import os.path
import base64
import re # Para expresiones regulares (extraer datos)
import logging # Para registrar información y errores

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import html2text

# --- CONFIGURACIÓN ---
# Si modificas estos SCOPES, elimina el archivo token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.modify', # Leer y modificar correos
          'https://www.googleapis.com/auth/spreadsheets'] # Escribir en Sheets

# ID de tu hoja de cálculo (de la URL)
# https://docs.google.com/spreadsheets/d/19DMRr2n_Xc7YF_9nKzpNaobgKw_s4fGWhmfJCPzIYNo/edit
SPREADSHEET_ID = '19DMRr2n_Xc7YF_9nKzpNaobgKw_s4fGWhmfJCPzIYNo'
# Nombre de la hoja + rango donde añadir datos. 'A1' asume columnas Fecha, Banco, Comercio, Tarjeta, Importe
SHEET_RANGE_NAME = 'Cuentas' 

GMAIL_LABEL_TO_SEARCH = 'tarjetas-consumos-tarjeta' # Etiqueta de donde leer
PROCESSED_LABEL_NAME = 'Procesado' # Etiqueta para marcar correos leídos
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

# Configuración de logging (cambiar a DEBUG para más detalle)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s')

# --- FUNCIONES AUXILIARES ---

def authenticate_google_apis():
    """Autentica al usuario y retorna los objetos de servicio para Gmail y Sheets."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.error(f"Error refrescando token: {e}. Necesita re-autorizar.")
                # Si falla el refresh, forzamos la re-autorización eliminando token.json
                if os.path.exists(TOKEN_FILE):
                    os.remove(TOKEN_FILE)
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    try:
        service_gmail = build('gmail', 'v1', credentials=creds)
        service_sheets = build('sheets', 'v4', credentials=creds)
        return service_gmail, service_sheets
    except HttpError as error:
        logging.error(f'Ocurrió un error al construir los servicios: {error}')
        return None, None

def get_or_create_label(service, user_id, label_name):
    """Obtiene el ID de una etiqueta o la crea si no existe."""
    try:
        results = service.users().labels().list(userId=user_id).execute()
        labels = results.get('labels', [])

        for label in labels:
            if label['name'] == label_name:
                logging.info(f"Etiqueta '{label_name}' encontrada con ID: {label['id']}")
                return label['id']

        # Si no se encontró, crearla
        logging.info(f"Etiqueta '{label_name}' no encontrada, creándola...")
        label_body = {
            'name': label_name,
            'labelListVisibility': 'labelShow',
            'messageListVisibility': 'show' # <--- ¡Aquí está el problema!
        }
        created_label = service.users().labels().create(userId=user_id, body=label_body).execute()
        logging.info(f"Etiqueta '{label_name}' creada con ID: {created_label['id']}")
        return created_label['id']

    except HttpError as error:
        logging.error(f'Ocurrió un error al obtener/crear la etiqueta {label_name}: {error}')
        return None

def parse_email_body(body_data):
    """Intenta decodificar el cuerpo del correo (usualmente Base64)."""
    if not body_data:
        logging.warning("parse_email_body recibió datos vacíos.")
        return None
    try:
        # Primero intenta decodificar como base64 urlsafe
        decoded_bytes = base64.urlsafe_b64decode(body_data.encode('ASCII'))
        # Luego intenta decodificar los bytes a texto (UTF-8 es común)
        decoded_text = decoded_bytes.decode('utf-8')
        logging.debug(f"Cuerpo decodificado (primeros 100 chars): {decoded_text[:100]}...")
        return decoded_text
    except base64.Error as b64_error:
        logging.warning(f"Error de decodificación Base64: {b64_error}. Intentando usar datos directamente.")
        # Si falla base64, podría ser texto plano no codificado (menos común)
        return body_data # Devuelve original, puede ser bytes o str
    except UnicodeDecodeError as unicode_error:
        logging.warning(f"Error de decodificación a texto (ej: UTF-8): {unicode_error}. Intentando otras codificaciones...")
        # Intentar con latin-1 como fallback común
        try:
            decoded_text = decoded_bytes.decode('latin-1')
            logging.debug(f"Cuerpo decodificado como latin-1 (primeros 100 chars): {decoded_text[:100]}...")
            return decoded_text
        except Exception as final_decode_error:
             logging.error(f"Fallo final de decodificación: {final_decode_error}")
             return None
    except Exception as e:
        logging.error(f"Error inesperado en parse_email_body: {e}")
        return None

def extract_data_from_email(message):
    """Extrae la información relevante del objeto mensaje de Gmail."""
    msg_id = message.get('id', 'N/A') # Obtener ID para logs
    logging.info(f"Procesando mensaje ID: {msg_id}")

    data = {'fecha': None, 'banco': None, 'comercio': None, 'tarjeta': None, 'importe': None, 'moneda': None}
    subject = ''
    sender = ''
    body_text = ''

    payload = message.get('payload', {})
    if not payload:
        logging.error(f"Mensaje {msg_id} no tiene payload.")
        return None

    headers = payload.get('headers', [])
    logging.debug(f"Mensaje {msg_id} - Payload MimeType: {payload.get('mimeType')}")

    # Extraer Asunto y Remitente
    for header in headers:
        name = header.get('name', '').lower()
        value = header.get('value', '')
        if name == 'subject':
            subject = value
            logging.debug(f"Mensaje {msg_id} - Asunto: {subject}")
        if name == 'from':
            sender = value
            logging.debug(f"Mensaje {msg_id} - Remitente: {sender}")
            # Determinar Banco basado en remitente (ajustar si es necesario)
            if 'bbva.com' in sender.lower():
                data['banco'] = 'BBVA'
            # Añadir más 'elif' para otros bancos

    # --- Lógica MEJORADA para extraer Cuerpo del Texto ---
    parts = payload.get('parts', [])
    body_data = None

    if parts:
        # Recorrer partes para encontrar text/plain o text/html
        logging.debug(f"Mensaje {msg_id} - Analizando {len(parts)} partes...")
        part_stack = list(parts) # Usar una pila para búsqueda en profundidad (maneja multipart anidados)
        found_plain = False

        while part_stack:
            part = part_stack.pop(0) # Procesar en orden (BFS-like)
            part_mime_type = part.get('mimeType', '').lower()
            logging.debug(f"  - Analizando parte con MimeType: {part_mime_type}")

            # Si es multipart, añadir sus sub-partes a la pila
            if 'multipart/' in part_mime_type:
                sub_parts = part.get('parts', [])
                if sub_parts:
                    logging.debug(f"    -> Encontrado multipart, añadiendo {len(sub_parts)} sub-partes.")
                    part_stack.extend(sub_parts) # Añadir al final para procesar después de hermanos
                continue # Pasar a la siguiente parte en la pila

            # Si encontramos text/plain, lo preferimos y paramos la búsqueda de texto
            if part_mime_type == 'text/plain':
                body = part.get('body', {})
                body_data = body.get('data')
                if body_data:
                    logging.info(f"Mensaje {msg_id} - Encontrado text/plain. Intentando decodificar.")
                    body_text = parse_email_body(body_data)
                    if body_text:
                        found_plain = True
                        break # Salir del while, ya tenemos el texto plano
                    else:
                        logging.warning(f"Mensaje {msg_id} - Falló la decodificación del text/plain.")
                        body_data = None # Resetear para posible fallback a HTML
                else:
                     logging.warning(f"Mensaje {msg_id} - Parte text/plain no tiene 'data' en 'body'.")

            # Si no hemos encontrado texto plano aún Y esta parte es text/html, la guardamos como fallback
            elif not found_plain and part_mime_type == 'text/html':
                body = part.get('body', {})
                html_body_data = body.get('data')
                if html_body_data:
                     logging.debug(f"Mensaje {msg_id} - Encontrado text/html como fallback.")
                     # Guardamos los datos crudos, solo decodificaremos si no encontramos plain text
                     body_data = html_body_data # Sobreescribe body_data si era None o falló text/plain
                else:
                    logging.warning(f"Mensaje {msg_id} - Parte text/html no tiene 'data' en 'body'.")


        # Si salimos del bucle y no encontramos texto plano, pero sí HTML, lo usamos
        if not found_plain and body_data:
             logging.info(f"Mensaje {msg_id} - No se encontró text/plain útil. Usando text/html como fallback.")
             body_text_html = parse_email_body(body_data)
             if body_text_html:
                # ----- NUEVO: Convertir HTML a texto plano -----
                try:
                    logging.debug(f"Mensaje {msg_id} - Iniciando conversión de HTML a texto plano.")
                    h = html2text.HTML2Text()
                    # Puedes configurar opciones, ej: ignorar enlaces o imágenes si no son relevantes
                    # h.ignore_links = True
                    # h.ignore_images = True
                    body_text = h.handle(body_text_html) # AQUÍ ocurre la conversión
                    logging.info(f"Mensaje {msg_id} - Conversión HTML a texto plano EXITOSA.")
                    logging.debug(f"--- INICIO TEXTO PLANO CONVERTIDO ({msg_id}) ---")
                    logging.debug(body_text[:1000] + "...") # Loguear más caracteres del resultado
                    logging.debug(f"--- FIN TEXTO PLANO CONVERTIDO ({msg_id}) ---")
                except Exception as e_conv:
                     logging.error(f"Mensaje {msg_id} - Error durante la conversión de HTML a texto: {e_conv}")
                     body_text = None # Si la conversión falla, no podemos continuar
                # ----- FIN NUEVO -----
             else:
                 logging.error(f"Mensaje {msg_id} - Falló la decodificación del text/html fallback.")
                 body_text = None # Asegurarse de que body_text sea None si la decodificación falló


    elif payload.get('body', {}).get('data'): # Para correos simples no multipart
        logging.info(f"Mensaje {msg_id} - Correo simple (no multipart). Intentando decodificar body principal.")
        body_data = payload.get('body', {}).get('data')
        # Aunque sea simple, podría ser HTML
        raw_body_text = parse_email_body(body_data)
        if raw_body_text:
             # Asumir que podría ser HTML y intentar convertir por si acaso
             # (Si ya es texto plano, html2text usualmente lo maneja bien)
             try:
                logging.debug(f"Mensaje {msg_id} - Procesando body simple (podría ser HTML).")
                h = html2text.HTML2Text()
                body_text = h.handle(raw_body_text)
                logging.info(f"Mensaje {msg_id} - Procesamiento de body simple OK.")
                logging.debug(f"--- INICIO TEXTO PLANO (simple) ({msg_id}) ---")
                logging.debug(body_text[:1000] + "...")
                logging.debug(f"--- FIN TEXTO PLANO (simple) ({msg_id}) ---")
             except Exception as e_conv_simple:
                logging.error(f"Mensaje {msg_id} - Error procesando body simple: {e_conv_simple}")
                body_text = None
        else:
            body_text = None

    # --- FIN Lógica de extracción de cuerpo ---


    if not body_text:
        # Este log ahora se genera solo si NINGÚN método funcionó O LA CONVERSIÓN FALLÓ
        logging.error(f"Mensaje {msg_id} - No se pudo extraer/convertir NINGÚN cuerpo de texto útil. Asunto: {subject}")
        logging.debug(f"Estructura del payload para {msg_id}: {payload}")
        return None # No se pudo procesar

    # --- EXTRACCIÓN CON EXPRESIONES REGULARES (Ajustadas para formato html2text) ---

    # Busca "Fecha", luego cualquier espacio (incl. saltos línea), luego "| **", captura la fecha, y termina con "**"
    fecha_match = re.search(
        r"Fecha"                # Literal "Fecha"
        r"\s+"                  # Uno o más espacios/saltos de línea
        r"\|\s*\*\*"            # Literal "|", espacio opcional, literal "**" (escapados)
        r"(\d{2}/\d{2}/\d{4})"  # Grupo 1: Captura la fecha DD/MM/AAAA
        r"\*\*"                 # Literal "**" de cierre
        , body_text, re.IGNORECASE | re.DOTALL) # DOTALL no es crucial aquí pero no daña

    # Busca "Comercio", espacio, "| **", captura cualquier caracter no goloso, y termina con "**"
    comercio_match = re.search(
        r"Comercio"             # Literal "Comercio"
        r"\s+"                  # Uno o más espacios/saltos de línea
        r"\|\s*\*\*"            # Literal "|", espacio opcional, literal "**"
        r"(.*?)"                # Grupo 1: Captura el nombre del comercio (no goloso)
        r"\*\*"                 # Literal "**" de cierre
        , body_text, re.IGNORECASE | re.DOTALL)

    # Busca "Importe", espacio, "| **", captura moneda, espacio, captura monto, y termina con "**"
    importe_match = re.search(
        r"Importe"              # Literal "Importe"
        r"\s+"                  # Uno o más espacios/saltos de línea
        r"\|\s*\*\*"            # Literal "|", espacio opcional, literal "**"
        r"(ARS|USD)\s*"         # Grupo 1: Captura moneda (ARS o USD) y espacio opcional
        r"([\d.,]+)"            # Grupo 2: Captura el número (con puntos o comas)
        r"\*\*"                 # Literal "**" de cierre
        , body_text, re.IGNORECASE | re.DOTALL)

    # --- Verificación y extracción de grupos (Asegúrate que los índices de grupo son correctos) ---
    if fecha_match:
        data['fecha'] = fecha_match.group(1) # Grupo 1 es la fecha
        logging.debug(f"Mensaje {msg_id} - Fecha encontrada: {data['fecha']}")
    else:
        logging.warning(f"Mensaje {msg_id} - No se encontró la fecha.")

    if comercio_match:
        data['comercio'] = comercio_match.group(1).strip() # Grupo 1 es el comercio
        logging.debug(f"Mensaje {msg_id} - Comercio encontrado: {data['comercio']}")
    else:
        logging.warning(f"Mensaje {msg_id} - No se encontró el comercio.")

    if importe_match:
        data['moneda'] = importe_match.group(1).upper() # Grupo 1 es la moneda
        importe_str = importe_match.group(2)           # Grupo 2 es el monto
        logging.debug(f"Mensaje {msg_id} - Importe encontrado (str): {importe_str}, Moneda: {data['moneda']}")
        # Limpieza del importe (sin cambios)
        importe_str_limpio = importe_str.replace('.', '').replace(',', '.')
        try:
            data['importe'] = float(importe_str_limpio)
            logging.debug(f"Mensaje {msg_id} - Importe (float): {data['importe']}")
        except ValueError:
            logging.error(f"Mensaje {msg_id} - No se pudo convertir el importe '{importe_str}' a número.")
            data['importe'] = None # Asegurarse de que quede None si falla la conversión
    else:
         logging.warning(f"Mensaje {msg_id} - No se encontró el importe.")

    # Extraer tipo de tarjeta (ej: del asunto)
    if 'visa' in subject.lower():
        data['tarjeta'] = 'VISA'
    elif 'mastercard' in subject.lower(): # Añadir otras si es necesario
        data['tarjeta'] = 'MASTERCARD'

    if data['tarjeta']:
         logging.debug(f"Mensaje {msg_id} - Tarjeta encontrada: {data['tarjeta']}")
    else:
         logging.warning(f"Mensaje {msg_id} - No se encontró el tipo de tarjeta en el asunto.")


    # Verificar si se extrajeron todos los datos necesarios
    datos_faltantes = [k for k, v in data.items() if v is None and k != 'moneda'] # Moneda es opcional si no se guarda
    if datos_faltantes:
        logging.error(f"Mensaje {msg_id} - Faltan datos al procesar correo: {datos_faltantes}. Asunto: {subject}. Datos extraídos: {data}")
        logging.debug(f"--- INICIO CUERPO TEXTO ({msg_id}) ---")
        logging.debug(body_text)
        logging.debug(f"--- FIN CUERPO TEXTO ({msg_id}) ---")
        # Aquí podrías llamar a una función para enviar notificación de error
        # send_error_notification(subject, body_text, data)
        return None # Indica que el parseo falló

    logging.info(f"Mensaje {msg_id} - Datos extraídos OK: {data}")
    return data


def append_to_sheet(service, spreadsheet_id, range_name, values):
    """Añade una fila de datos a la hoja de cálculo."""
    try:
        body = {
            'values': [values] # values debe ser una lista de listas
        }
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='USER_ENTERED', # O 'RAW' si no necesitas que Sheets interprete
            insertDataOption='INSERT_ROWS',
            body=body
        ).execute()
        logging.info(f"{result.get('updates').get('updatedCells')} celdas añadidas.")
        return True
    except HttpError as error:
        logging.error(f'Ocurrió un error al añadir datos a Sheets: {error}')
        return False

def mark_email_processed(service, user_id, msg_id, processed_label_id):
    """Marca un correo como leído y le añade la etiqueta 'Procesado'."""
    try:
        body = {
            'removeLabelIds': ['UNREAD'],
            'addLabelIds': [processed_label_id]
        }
        service.users().messages().modify(userId=user_id, id=msg_id, body=body).execute()
        logging.info(f"Correo {msg_id} marcado como leído y etiquetado como '{PROCESSED_LABEL_NAME}'.")
        return True
    except HttpError as error:
        logging.error(f'Ocurrió un error al modificar el correo {msg_id}: {error}')
        return False

# --- FUNCIÓN PRINCIPAL ---
def main():
    logging.info("Iniciando proceso de lectura de consumos...")
    service_gmail, service_sheets = authenticate_google_apis()

    if not service_gmail or not service_sheets:
        logging.error("No se pudieron obtener los servicios de Google. Saliendo.")
        return

    user_id = 'me'
    processed_label_id = get_or_create_label(service_gmail, user_id, PROCESSED_LABEL_NAME)
    if not processed_label_id:
        logging.error("No se pudo obtener o crear la etiqueta 'Procesado'. Saliendo.")
        return

    # Buscar correos no leídos en la etiqueta específica, que NO tengan la etiqueta 'Procesado'
    query = f'label:"{GMAIL_LABEL_TO_SEARCH}" is:unread -label:"{PROCESSED_LABEL_NAME}"'
    try:
        results = service_gmail.users().messages().list(userId=user_id, q=query).execute()
        messages = results.get('messages', [])

        if not messages:
            logging.info("No se encontraron correos nuevos para procesar.")
            return

        logging.info(f"Se encontraron {len(messages)} correos para procesar.")

        for message_info in messages:
            msg_id = message_info['id']
            try:
                # Obtener el contenido completo del correo
                message = service_gmail.users().messages().get(userId=user_id, id=msg_id, format='full').execute() # format='full' para headers y body

                # Extraer los datos
                extracted_data = extract_data_from_email(message)

                if extracted_data:
                    # Preparar fila para Google Sheets
                    # Columnas: Fecha / Banco /Comercio / Tarjeta (VISA o MASTERCARD) / Importe
                    # Nota: La moneda (ARS/USD) no está en las columnas pedidas, solo el importe numérico.
                    row_values = [
                        extracted_data['fecha'],
                        extracted_data['banco'],
                        extracted_data['comercio'],
                        extracted_data['tarjeta'],
                        extracted_data['importe'] # Ya es un float
                    ]

                    # Añadir a Google Sheets
                    if append_to_sheet(service_sheets, SPREADSHEET_ID, SHEET_RANGE_NAME, row_values):
                        # Marcar correo como procesado (leído + etiqueta)
                        mark_email_processed(service_gmail, user_id, msg_id, processed_label_id)
                    else:
                        logging.error(f"No se pudo añadir a Sheets el correo {msg_id}. No se marcará como procesado.")
                else:
                    # El parseo falló, se loggeó dentro de extract_data_from_email
                    # Considera enviar notificación aquí o dentro de la función de parseo
                    logging.warning(f"No se procesó el correo {msg_id} debido a errores de extracción.")
                    # Podrías decidir marcarlo como procesado igualmente para no reintentar, o dejarlo sin procesar.
                    # Por seguridad, no lo marcamos si falló el parseo.

            except HttpError as error:
                logging.error(f'Ocurrió un error al procesar el correo {msg_id}: {error}')
            except Exception as e:
                 logging.error(f'Ocurrió un error inesperado al procesar el correo {msg_id}: {e}', exc_info=True)


    except HttpError as error:
        logging.error(f'Ocurrió un error al buscar correos: {error}')
    except Exception as e:
        logging.error(f'Ocurrió un error inesperado en la búsqueda de correos: {e}', exc_info=True)

    logging.info("Proceso de lectura de consumos finalizado.")

# --- EJECUCIÓN ---
if __name__ == '__main__':
    main()