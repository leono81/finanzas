## Documentación Técnica para Prompts de IA: procesar_consumos.py

**Nombre del Script:** `procesar_consumos.py`

**Objetivo Principal:**
Este script de Python está diseñado para automatizar la extracción de datos de consumo de tarjetas de crédito/débito desde correos electrónicos de Gmail. Procesa estos correos, extrae información clave (fecha, banco, comercio, tarjeta, importe, moneda), y registra estos datos en una Hoja de Cálculo de Google especificada. Adicionalmente, maneja la categorización de gastos (a través de una tabla de mapeo en Google Sheets), la autenticación con APIs de Google, y la rotación de logs.

**Componentes Clave y Lógica del Script:**

1.  **Autenticación (`authenticate_google_apis` function):**
    *   Utiliza OAuth 2.0. Requiere un archivo `credentials.json` del Google Cloud Project.
    *   Genera y utiliza un archivo `token.json` para almacenar los tokens de acceso y refresco.
    *   Scopes de API solicitados: `https://www.googleapis.com/auth/gmail.modify`, `https://www.googleapis.com/auth/spreadsheets`.
    *   Construye y retorna objetos de servicio para Gmail API v1 y Sheets API v4.

2.  **Manejo de Etiquetas de Gmail (`get_or_create_label` function):**
    *   Obtiene el ID de una etiqueta de Gmail por su nombre.
    *   Si la etiqueta no existe, la crea. Usado para la etiqueta `PROCESSED_LABEL_NAME`.

3.  **Flujo Principal de Procesamiento (función `main`):**
    *   Autentica con las APIs de Google.
    *   Obtiene/Crea el ID de la etiqueta para correos procesados.
    *   Construye una consulta de Gmail para buscar correos no leídos en `GMAIL_LABEL_TO_SEARCH` que no tengan la etiqueta `PROCESSED_LABEL_NAME`.
        *   Query: `f'label:"{GMAIL_LABEL_TO_SEARCH}" is:unread -label:"{PROCESSED_LABEL_NAME}"'`
    *   Itera sobre cada mensaje encontrado:
        *   Obtiene el contenido completo del mensaje (`format='full'`).
        *   Llama a `extract_data_from_email(message)` para obtener los datos estructurados.
        *   Si `extract_data_from_email` retorna datos válidos:
            *   Prepara `row_values` en el orden: Fecha, Banco, Comercio, Tarjeta, Importe.
            *   Llama a `append_to_sheet()` para escribir la fila en Google Sheets.
            *   Si `append_to_sheet()` es exitoso, llama a `mark_email_processed()` para actualizar las etiquetas del correo en Gmail.
        *   Maneja errores durante el procesamiento de cada correo.

4.  **Extracción de Datos del Email (`extract_data_from_email` function):**
    *   Inicializa un diccionario `data` con claves: `fecha`, `banco`, `comercio`, `tarjeta`, `importe`, `moneda`.
    *   **Cabeceras:** Extrae `Subject`, `From` y `Date` (para obtener el año `email_year`). Si el año no se puede extraer del header, usa el año actual.
    *   **Identificación del Banco:** Se basa en el dominio del email del remitente (ej., `'bbva.com'` -> `BBVA`, `'naranjax.com'` -> `Naranja X`).
    *   **Procesamiento del Cuerpo del Email:**
        *   Intenta obtener `text/plain` primero.
        *   Si `text/plain` no está disponible o falla la decodificación, intenta con `text/html`.
        *   `parse_email_body(body_data)`: Decodifica los datos del cuerpo (Base64 urlsafe, luego UTF-8, con fallback a latin-1).
        *   Si el cuerpo es HTML, se convierte a texto plano usando `html2text.HTML2Text(ignore_links=True, ignore_images=True)`.
    *   **Extracción Específica por Banco (usando Regex sobre `body_text`):**
        *   **Naranja X:**
            *   Importe: `r"\$(\d[\d.,]+)"`
            *   Comercio: `r"\$[\d.,]+\s*(.*?)\s+Titular\s+-"` (primario) o `r"\$[\d.,]+\s*(.*?)\s+Tarjeta\s+VISA"` (fallback).
            *   Tarjeta: `r"Tarjeta\s+(VISA|MASTERCARD)"`
            *   Fecha: `r"(\d{1,2})/([A-Z]{3})"`, usa `MESES_MAP` y `email_year` para formatear a `DD/MM/YYYY`.
            *   Moneda: Inferida (ARS por defecto o si "PESOS" está presente, USD si "USD" está presente).
        *   **BBVA:**
            *   Diseñado para el formato de tabla Markdown generado por `html2text`.
            *   Fecha: `r"Fecha\s+\|\s*\*\*(.*?)\*\*"`
            *   Comercio: `r"Comercio\s+\|\s*\*\*(.*?)\*\*"`
            *   Importe: `r"Importe\s+\|\s*\*\*(ARS|USD)\s*([\d.,]+)\*\*"`
            *   Tarjeta: Inferida del `subject` del email (`visa` o `mastercard`).
        *   Si el banco es desconocido, la función retorna `None`.
    *   **Limpieza y Verificación:** Convierte el importe a `float`. Verifica que los campos obligatorios (todos excepto `moneda` potencialmente) hayan sido extraídos.

5.  **Escritura en Google Sheets (`append_to_sheet` function):**
    *   Usa `service.spreadsheets().values().append()`.
    *   Parámetros: `spreadsheetId=SPREADSHEET_ID`, `range=SHEET_RANGE_NAME`, `valueInputOption='USER_ENTERED'`, `insertDataOption='INSERT_ROWS'`.
    *   El `range` actual (`Data_Emails`) implica que se añade a la primera tabla encontrada en esa hoja o después de la última fila con contenido.

6.  **Marcado de Emails (`mark_email_processed` function):**
    *   Usa `service.users().messages().modify()`.
    *   Elimina la etiqueta `'UNREAD'`.
    *   Añade la etiqueta `processed_label_id`.

7.  **Configuración de Logging:**
    *   Utiliza `logging.handlers.TimedRotatingFileHandler`.
    *   El logger raíz está configurado.
    *   Nivel: `logging.INFO`.
    *   Formato: `%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s`.
    *   **Salida a Consola:** `logging.StreamHandler()`.
    *   **Salida a Archivo Rotativo:**
        *   Archivo: `LOG_FILE_NAME` (configurable).
        *   Rotación: Diaria (`when='D'`, `interval=1`).
        *   Retención: `backupCount=LOG_RETENTION_DAYS` (configurable).
        *   Encoding: `utf-8`.

**Variables de Configuración Global Clave:**

*   `SCOPES`: Lista de strings.
*   `SPREADSHEET_ID`: String.
*   `SHEET_RANGE_NAME`: String (nombre de la hoja, ej: `'Data_Emails'`).
*   `GMAIL_LABEL_TO_SEARCH`: String.
*   `PROCESSED_LABEL_NAME`: String.
*   `CREDENTIALS_FILE`: String (path, por defecto `'credentials.json'`).
*   `TOKEN_FILE`: String (path, por defecto `'token.json'`).
*   `MESES_MAP`: Diccionario `{'MES_ABBR': 'MM'}`.
*   `LOG_FILE_NAME`: String.
*   `LOG_RETENTION_DAYS`: Integer.

**Estructura de Datos Esperada en Google Sheets (Hoja `Data_Emails`):**

*   Columna A: Fecha (String, formato `DD/MM/YYYY`)
*   Columna B: Banco (String)
*   Columna C: Comercio (String)
*   Columna D: Tarjeta (String, "VISA" o "MASTERCARD")
*   Columna E: Importe (Float)

**Puntos Típicos de Modificación/Extensión:**

*   **Soporte para un Nuevo Banco:**
    1.  En `extract_data_from_email`: Añadir una condición `elif` para el nuevo dominio del remitente en la sección de identificación del banco.
    2.  En `extract_data_from_email`: Añadir una nueva sección `elif data['banco'] == 'NombreNuevoBanco':` con la lógica de expresiones regulares y extracción específica para los correos de ese banco.
*   **Ajustar Extracción para Banco Existente:**
    1.  Modificar las expresiones regulares y la lógica asociada dentro de la sección del banco correspondiente en `extract_data_from_email`.
*   **Cambiar Columnas o Formato de Salida en Google Sheets:**
    1.  Modificar la creación de `row_values` en la función `main`.
    2.  Si se añaden/quitan columnas, la hoja `Data_Emails` y las fórmulas dependientes en Google Sheets (`Cuentas`, `Data_Formulario_Preparada`) necesitarán ajuste.
*   **Modificar Configuración de Logs:**
    1.  Cambiar `LOG_RETENTION_DAYS`.
    2.  Ajustar parámetros de `TimedRotatingFileHandler` (ej., `when`, `interval`) para diferentes estrategias de rotación.
*   **Cambiar Criterios de Búsqueda de Emails:**
    1.  Modificar la variable `query` en la función `main`.