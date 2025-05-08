import os.path
import base64
import re # Para expresiones regulares (extraer datos)
import logging # Para registrar información y errores
import html2text # Para convertir HTML a texto
import datetime # Para obtener el año actual si falla la extracción del header
import logging.handlers # <--- AÑADIR ESTE IMPORT

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- CONFIGURACIÓN ---
# Si modificas estos SCOPES, elimina el archivo token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.modify', # Leer y modificar correos
          'https://www.googleapis.com/auth/spreadsheets'] # Escribir en Sheets

# ID de tu hoja de cálculo (de la URL)
# https://docs.google.com/spreadsheets/d/19DMRr2n_Xc7YF_9nKzpNaobgKw_s4fGWhmfJCPzIYNo/edit
SPREADSHEET_ID = '19DMRr2n_Xc7YF_9nKzpNaobgKw_s4fGWhmfJCPzIYNo'
# Nombre de la hoja + rango donde añadir datos. 'A1' asume columnas Fecha, Banco, Comercio, Tarjeta, Importe
SHEET_RANGE_NAME = 'Data_Emails' 

GMAIL_LABEL_TO_SEARCH = 'tarjetas-consumos-tarjeta' # Etiqueta de donde leer (formato para API/búsqueda)
PROCESSED_LABEL_NAME = 'Procesado' # Etiqueta para marcar correos leídos
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

# Mapa de meses abreviados a números (para Naranja X)
MESES_MAP = {'ENE': '01', 'FEB': '02', 'MAR': '03', 'ABR': '04', 'MAY': '05', 'JUN': '06', 'JUL': '07', 'AGO': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DIC': '12'}

# --- NUEVA CONFIGURACIÓN DE LOGS ---
LOG_FILE_NAME = 'procesar_consumos.log' # Nombre del archivo de log
LOG_RETENTION_DAYS = 14 # Número de días de logs a retener (ej: 14 para 2 semanas, 7 para 1 semana)
# --- FIN NUEVA CONFIGURACIÓN DE LOGS ---

# Configuración de logging (SE REEMPLAZARÁ/MODIFICARÁ LA SIGUIENTE LÍNEA)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s')

# --- NUEVA CONFIGURACIÓN DETALLADA DE LOGGING ---
logger = logging.getLogger() # Obtener el logger raíz
logger.setLevel(logging.INFO) # Establecer el nivel mínimo de logging

# Formateador para los logs
formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s')

# Manejador para la consola (opcional, si aún quieres ver logs en la consola)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Manejador para el archivo con rotación de tiempo
# Rota diariamente ('D'), mantiene LOG_RETENTION_DAYS archivos de respaldo.
# El archivo de log activo será LOG_FILE_NAME, los antiguos serán LOG_FILE_NAME.YYYY-MM-DD
file_handler = logging.handlers.TimedRotatingFileHandler(
    LOG_FILE_NAME,
    when='D',           # 'D' para diario, 'H' para horario, 'W0'-'W6' para semanal (Lunes-Domingo), 'M' para minuto
    interval=1,         # Intervalo para 'when'. 1 para diario significa cada 1 día.
    backupCount=LOG_RETENTION_DAYS, # Número de archivos de respaldo a mantener
    encoding='utf-8',   # Buena práctica especificar encoding
    delay=False         # Si es True, la creación del archivo de log se pospone hasta la primera emisión
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
# --- FIN NUEVA CONFIGURACIÓN DETALLADA DE LOGGING ---

# --- FUNCIONES AUXILIARES ---

import os
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Asegúrate de que estas constantes estén definidas globalmente ---
TOKEN_FILE = 'token.json'
CREDENTIALS_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/spreadsheets']
# ---



def authenticate_google_apis():
    """Autentica al usuario y retorna los objetos de servicio para Gmail y Sheets.
       Usa flujo manual de consola si es necesario."""
    creds = None
    # 1. Intenta cargar el token existente
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            logging.info(f"Token cargado desde {TOKEN_FILE}")
        except Exception as e:
            logging.warning(f"Error al cargar {TOKEN_FILE}: {e}. Se intentará re-autenticar.")
            try:
                os.remove(TOKEN_FILE)
                logging.info(f"Archivo {TOKEN_FILE} corrupto eliminado.")
            except OSError:
                pass
            creds = None

    # 2. Si no hay credenciales o no son válidas, intentar refrescar o re-autenticar
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logging.info("Credenciales expiradas, intentando refrescar...")
            try:
                creds.refresh(Request())
                logging.info("¡Token refrescado exitosamente!")
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
                logging.info(f"Token refrescado guardado en {TOKEN_FILE}")
            except Exception as e:
                logging.error(f"Error al refrescar el token: {e}. Se requiere re-autenticación.")
                try:
                    os.remove(TOKEN_FILE)
                    logging.info(f"Archivo {TOKEN_FILE} inválido eliminado.")
                except OSError:
                    pass
                creds = None
        else:
            logging.info("No hay credenciales válidas o no se pueden refrescar. Iniciando flujo de autenticación manual por consola.")
            creds = None

    # 3. Si después de todo lo anterior no hay credenciales válidas, ejecutar flujo MANUAL de consola
    if not creds:
        try:
            # --- Flujo Manual de Consola ---
            logging.info("Iniciando flujo de autenticación manual...")
            # Especificar redirect_uri para flujo manual OOB (out-of-band)
            redirect_uri_oob = 'urn:ietf:wg:oauth:2.0:oob'
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE,
                SCOPES,
                redirect_uri=redirect_uri_oob # <<< URI para flujo OOB
            )

            # Generar la URL de autorización
            # access_type='offline' asegura que obtengamos un refresh_token
            auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

            # Imprimir la URL para el usuario
            print('=' * 80)
            print('Por favor, visita esta URL en tu navegador local para autorizar esta aplicación:')
            print(auth_url)
            print('=' * 80)
            print('Después de autorizar, copia el código proporcionado por Google.')
            print("-" * 30)

            # Pedir al usuario que pegue el código
            code = input('Ingresa el código de autorización obtenido en el navegador y presiona Enter: ')
            code = code.strip() # Quitar espacios extra
            print("-" * 30)

            # Intercambiar el código por tokens
            logging.info("Código recibido, intercambiando por tokens...")
            flow.fetch_token(code=code)
            creds = flow.credentials # Obtener las credenciales del flujo
            logging.info("¡Tokens obtenidos exitosamente!")

            # Guardar las nuevas credenciales
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
            logging.info(f"Autenticación manual exitosa. Token guardado en {TOKEN_FILE}")

        except FileNotFoundError:
            logging.critical(f"ERROR CRÍTICO: No se encontró el archivo de credenciales '{CREDENTIALS_FILE}'. Descárgalo desde Google Cloud Console y colócalo en la misma carpeta que el script.")
            return None, None
        except Exception as e:
            logging.error(f"Error durante el flujo de autenticación manual por consola: {e}", exc_info=True)
            return None, None

    # 4. Construir y devolver los servicios
    try:
        if not creds: # Doble chequeo por si falló la autenticación manual
             logging.error("No se pudieron obtener credenciales válidas.")
             return None, None

        service_gmail = build('gmail', 'v1', credentials=creds)
        service_sheets = build('sheets', 'v4', credentials=creds)
        logging.info("Servicios de Gmail y Sheets construidos exitosamente.")
        return service_gmail, service_sheets
    except HttpError as error:
        logging.error(f'Ocurrió un error al construir los servicios: {error}')
        return None, None
    except Exception as e:
        logging.error(f'Error inesperado al construir servicios: {e}', exc_info=True)
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
    email_year = None # Para guardar el año extraído del header

    payload = message.get('payload', {})
    if not payload:
        logging.error(f"Mensaje {msg_id} no tiene payload.")
        return None

    headers = payload.get('headers', [])
    logging.debug(f"Mensaje {msg_id} - Payload MimeType: {payload.get('mimeType')}")

    # --- Extracción de Headers Clave (Remitente, Asunto, Fecha) ---
    for header in headers:
        name = header.get('name', '').lower()
        value = header.get('value', '')
        if name == 'subject':
            subject = value
            logging.debug(f"Mensaje {msg_id} - Asunto: {subject}")
        elif name == 'from':
            sender = value
            logging.debug(f"Mensaje {msg_id} - Remitente: {sender}")
            # --- Identificación del Banco ---
            if 'bbva.com' in sender.lower():
                data['banco'] = 'BBVA'
            elif 'naranjax.com' in sender.lower(): # NUEVO
                data['banco'] = 'Naranja X'      # NUEVO
            else:
                 logging.warning(f"Mensaje {msg_id} - Banco no reconocido para remitente: {sender}")
                 data['banco'] = 'Desconocido'
        elif name == 'date':
             # Extraer año del header Date
             date_str = value
             year_match = re.search(r'(\d{4})', date_str)
             if year_match:
                 email_year = year_match.group(1)
                 logging.debug(f"Mensaje {msg_id} - Año extraído del header 'Date': {email_year}")

    # Si no se pudo extraer el año, usar el actual como fallback
    if not email_year:
        logging.warning(f"Mensaje {msg_id} - No se pudo extraer el año del header 'Date'. Usando año actual como fallback.")
        email_year = str(datetime.datetime.now().year)

    # --- Lógica MEJORADA para extraer Cuerpo del Texto (Prioriza text/plain) ---
    parts = payload.get('parts', [])
    plain_body_text = None
    html_body_data = None # Guardará los datos crudos del HTML si se encuentra
    found_plain_successfully = False

    if parts:
        logging.debug(f"Mensaje {msg_id} - Analizando {len(parts)} partes...")
        part_stack = list(parts)

        while part_stack:
            part = part_stack.pop(0)
            part_mime_type = part.get('mimeType', '').lower()
            logging.debug(f"  - Analizando parte con MimeType: {part_mime_type}")

            if 'multipart/' in part_mime_type:
                sub_parts = part.get('parts', [])
                if sub_parts:
                    logging.debug(f"    -> Encontrado multipart, añadiendo {len(sub_parts)} sub-partes.")
                    part_stack.extend(sub_parts)
                continue

            # Prioridad 1: text/plain
            if part_mime_type == 'text/plain' and not found_plain_successfully: # Solo procesa el primero útil
                body = part.get('body', {})
                body_data = body.get('data')
                if body_data:
                    logging.info(f"Mensaje {msg_id} - Encontrado text/plain. Intentando decodificar.")
                    decoded_plain = parse_email_body(body_data)
                    if decoded_plain:
                        plain_body_text = decoded_plain # Guardar texto plano decodificado
                        found_plain_successfully = True
                        logging.info(f"Mensaje {msg_id} - Decodificación text/plain EXITOSA.")
                        # No rompemos el bucle, por si hay un HTML mejor formateado (poco probable, pero por completitud)
                    else:
                        logging.warning(f"Mensaje {msg_id} - Falló la decodificación del text/plain.")
                else:
                     logging.warning(f"Mensaje {msg_id} - Parte text/plain no tiene 'data' en 'body'.")

            # Prioridad 2: text/html (guardar datos para fallback)
            elif part_mime_type == 'text/html':
                 body = part.get('body', {})
                 html_body_data_candidate = body.get('data')
                 if html_body_data_candidate:
                     html_body_data = html_body_data_candidate # Guardar datos crudos del HTML
                     logging.debug(f"Mensaje {msg_id} - Encontrado text/html (para posible fallback).")
                 else:
                    logging.warning(f"Mensaje {msg_id} - Parte text/html no tiene 'data' en 'body'.")

    # --- Decidir qué cuerpo usar ---
    if found_plain_successfully:
        logging.info(f"Mensaje {msg_id} - Usando contenido text/plain.")
        body_text = plain_body_text
        logging.debug(f"--- INICIO TEXTO PLANO ({msg_id}) ---")
        logging.debug(body_text[:1000] + "...")
        logging.debug(f"--- FIN TEXTO PLANO ({msg_id}) ---")
    elif html_body_data:
        logging.info(f"Mensaje {msg_id} - No se encontró/decodificó text/plain útil. Usando fallback text/html.")
        body_text_html = parse_email_body(html_body_data)
        if body_text_html:
            try:
                logging.debug(f"Mensaje {msg_id} - Iniciando conversión de HTML a texto plano.")
                h = html2text.HTML2Text()
                h.ignore_links = True # Ignorar enlaces puede limpiar el output
                h.ignore_images = True # Ignorar imágenes
                body_text = h.handle(body_text_html)
                logging.info(f"Mensaje {msg_id} - Conversión HTML a texto plano EXITOSA.")
                logging.debug(f"--- INICIO TEXTO PLANO CONVERTIDO ({msg_id}) ---")
                logging.debug(body_text[:1000] + "...")
                logging.debug(f"--- FIN TEXTO PLANO CONVERTIDO ({msg_id}) ---")
            except Exception as e_conv:
                 logging.error(f"Mensaje {msg_id} - Error durante la conversión de HTML a texto: {e_conv}")
                 body_text = None
        else:
             logging.error(f"Mensaje {msg_id} - Falló la decodificación del text/html fallback.")
             body_text = None
    elif payload.get('body', {}).get('data'): # Correos simples (poco probable para estos bancos)
        # ... (lógica similar para procesar body simple, intentar convertir a texto) ...
        logging.warning(f"Mensaje {msg_id} - Procesando como correo simple (no multipart).")
        raw_body_text = parse_email_body(payload.get('body', {}).get('data'))
        if raw_body_text:
            try:
                h = html2text.HTML2Text()
                h.ignore_links = True
                h.ignore_images = True
                body_text = h.handle(raw_body_text) # Intentar convertir por si es HTML
            except Exception as e_conv_simple:
                logging.error(f"Mensaje {msg_id} - Error procesando body simple: {e_conv_simple}")
                body_text = None
        else: body_text = None


    # --- Fin Lógica de extracción de cuerpo ---

    if not body_text:
        logging.error(f"Mensaje {msg_id} - No se pudo extraer/convertir NINGÚN cuerpo de texto útil. Asunto: {subject}")
        logging.debug(f"Estructura del payload para {msg_id}: {payload}")
        return None # No se pudo procesar

    # --- EXTRACCIÓN CON EXPRESIONES REGULARES (CONDICIONAL POR BANCO) ---
    try:
        if data['banco'] == 'Naranja X':
            logging.info(f"Mensaje {msg_id} - Aplicando reglas de extracción para Naranja X.")
            # Regex para Naranja X (aplicadas a body_text, que debería ser el text/plain)

            # Importe: Busca $ seguido de números con . y ,
            importe_match = re.search(r"\$(\d[\d.,]+)", body_text)
            # Comercio: Busca el importe, captura cualquier caracter (no goloso) hasta encontrar "Titular -"
            comercio_match = re.search(
                r"\$[\d.,]+"       # Encuentra el importe $17.000,00
                r"\s*"             # Cero o más espacios/saltos de línea después
                r"(.*?)"           # Grupo 1: Captura el nombre del comercio (no goloso)
                r"\s+Titular\s+-"  # Detente cuando encuentres espacio(s), "Titular", espacio(s) y "-"
                , body_text, re.DOTALL) # re.DOTALL permite a '.' incluir saltos de línea si los hubiera

            if comercio_match:
                data['comercio'] = comercio_match.group(1).strip() # Captura Grupo 1 y limpia espacios
                logging.debug(f"Mensaje {msg_id} [NX] - Comercio encontrado: {data['comercio']}")
            else:
                # Si aún falla, podríamos intentar buscar entre el importe y "Tarjeta VISA" como último recurso
                comercio_match_alt = re.search(r"\$[\d.,]+\s*(.*?)\s+Tarjeta\s+VISA", body_text, re.DOTALL)
                if comercio_match_alt:
                     data['comercio'] = comercio_match_alt.group(1).strip()
                     logging.debug(f"Mensaje {msg_id} [NX] - Comercio encontrado (fallback Tarjeta): {data['comercio']}")
                else:
                    logging.warning(f"Mensaje {msg_id} [NX] - No se encontró el comercio (ni primario ni fallback).")

            # Tarjeta: Busca "Tarjeta" seguido de VISA o MASTERCARD
            tarjeta_match = re.search(r"Tarjeta\s+(VISA|MASTERCARD)", body_text, re.IGNORECASE)
            # Fecha: Busca el patrón Día/MesAbbr
            fecha_dia_mes_match = re.search(r"(\d{1,2})/([A-Z]{3})", body_text, re.IGNORECASE)

            if importe_match:
                importe_str = importe_match.group(1)
                logging.debug(f"Mensaje {msg_id} [NX] - Importe encontrado (str): {importe_str}")
                importe_str_limpio = importe_str.replace('.', '').replace(',', '.')
                data['importe'] = float(importe_str_limpio)
                # Asumir ARS si ve "PESOS" o si no especifica USD explícitamente
                if "PESOS" in body_text.upper() or "USD" not in body_text.upper():
                     data['moneda'] = 'ARS'
                elif "USD" in body_text.upper(): # O buscar U$S?
                    data['moneda'] = 'USD'
                logging.debug(f"Mensaje {msg_id} [NX] - Importe (float): {data['importe']}, Moneda: {data['moneda']}")
            else:
                logging.warning(f"Mensaje {msg_id} [NX] - No se encontró el importe.")

            if tarjeta_match:
                data['tarjeta'] = tarjeta_match.group(1).upper()
                logging.debug(f"Mensaje {msg_id} [NX] - Tarjeta encontrada: {data['tarjeta']}")
            else:
                logging.warning(f"Mensaje {msg_id} [NX] - No se encontró el tipo de tarjeta.")

            if fecha_dia_mes_match:
                 dia = fecha_dia_mes_match.group(1).zfill(2)
                 mes_abbr = fecha_dia_mes_match.group(2).upper()
                 mes_num = MESES_MAP.get(mes_abbr)
                 if mes_num:
                     data['fecha'] = f"{dia}/{mes_num}/{email_year}" # Usar año del header
                     logging.debug(f"Mensaje {msg_id} [NX] - Fecha encontrada: {data['fecha']}")
                 else:
                     logging.warning(f"Mensaje {msg_id} [NX] - Abreviatura de mes no reconocida: {mes_abbr}")
            else:
                 logging.warning(f"Mensaje {msg_id} [NX] - No se encontró la fecha (Día/Mes).")


        elif data['banco'] == 'BBVA':
            logging.info(f"Mensaje {msg_id} - Aplicando reglas de extracción para BBVA.")
            # Regex para BBVA (aplicadas a body_text, que debería ser el resultado de html2text)
            # (Usar las regex que ya funcionaban para BBVA)
            fecha_match = re.search(r"Fecha\s+\|\s*\*\*(.*?)\*\*", body_text, re.IGNORECASE | re.DOTALL) # Ajustada ligeramente
            comercio_match = re.search(r"Comercio\s+\|\s*\*\*(.*?)\*\*", body_text, re.IGNORECASE | re.DOTALL) # Ajustada ligeramente
            importe_match = re.search(r"Importe\s+\|\s*\*\*(ARS|USD)\s*([\d.,]+)\*\*", body_text, re.IGNORECASE | re.DOTALL) # Ajustada ligeramente

            if fecha_match:
                data['fecha'] = fecha_match.group(1).strip()
                logging.debug(f"Mensaje {msg_id} [BBVA] - Fecha encontrada: {data['fecha']}")
            else: logging.warning(f"Mensaje {msg_id} [BBVA] - No se encontró la fecha.")

            if comercio_match:
                data['comercio'] = comercio_match.group(1).strip()
                logging.debug(f"Mensaje {msg_id} [BBVA] - Comercio encontrado: {data['comercio']}")
            else: logging.warning(f"Mensaje {msg_id} [BBVA] - No se encontró el comercio.")

            if importe_match:
                data['moneda'] = importe_match.group(1).upper()
                importe_str = importe_match.group(2).strip()
                logging.debug(f"Mensaje {msg_id} [BBVA] - Importe encontrado (str): {importe_str}, Moneda: {data['moneda']}")
                importe_str_limpio = importe_str.replace('.', '').replace(',', '.')
                data['importe'] = float(importe_str_limpio)
                logging.debug(f"Mensaje {msg_id} [BBVA] - Importe (float): {data['importe']}")
            else: logging.warning(f"Mensaje {msg_id} [BBVA] - No se encontró el importe.")

            # Tarjeta para BBVA (asumimos del asunto)
            if 'visa' in subject.lower(): data['tarjeta'] = 'VISA'
            elif 'mastercard' in subject.lower(): data['tarjeta'] = 'MASTERCARD'
            if data['tarjeta']: logging.debug(f"Mensaje {msg_id} [BBVA] - Tarjeta encontrada (asunto): {data['tarjeta']}")
            else: logging.warning(f"Mensaje {msg_id} [BBVA] - No se encontró tarjeta en asunto.")


        else: # Banco desconocido o no configurado
            logging.error(f"Mensaje {msg_id} - No hay reglas de extracción definidas para el banco: {data['banco']}")
            return None

    except Exception as e_regex:
         logging.error(f"Mensaje {msg_id} - Error durante la aplicación de regex para banco {data['banco']}: {e_regex}", exc_info=True)
         return None

    # --- Verificación final de datos ---
    datos_faltantes = [k for k, v in data.items() if v is None and k != 'moneda'] # Moneda es opcional si no se guarda
    if datos_faltantes:
        logging.error(f"Mensaje {msg_id} - Faltan datos OBLIGATORIOS al procesar correo: {datos_faltantes}. Banco: {data['banco']}, Asunto: {subject}. Datos extraídos: {data}")
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
