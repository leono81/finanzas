# Automatización de Registro de Consumos Financieros

Este script de Python lee correos electrónicos de confirmación de compras con tarjeta de crédito desde una etiqueta específica en Gmail, extrae los detalles de la compra (Fecha, Banco, Comercio, Tarjeta, Importe) y los añade como una nueva fila en una hoja de cálculo de Google Sheets.

Actualmente está configurado para correos de BBVA Argentina, pero puede adaptarse a otros bancos modificando las expresiones regulares de extracción.

## Prerrequisitos

*   Python 3.x
*   Cuenta de Google
*   Un proyecto en Google Cloud Platform
*   APIs de Gmail y Google Sheets habilitadas en GCP
*   Una etiqueta en Gmail donde lleguen los correos de consumo (ej: `Tarjetas/Consumos Tarjeta`).
*   Una hoja de cálculo en Google Sheets con una pestaña para registrar los datos (ej: `Cuentas`) y columnas (ej: Fecha, Banco, Comercio, Tarjeta, Importe).

## Configuración

1.  **Clonar el repositorio:**
    ```bash
    git clone https://github.com/leono81/finanzas.git
    cd finanzas
    ```

2.  **Crear y activar un entorno virtual (recomendado):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # En Linux/macOS
    # o .\venv\Scripts\activate  # En Windows PowerShell
    ```

3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configuración de Google Cloud Platform:**
    *   Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com/).
    *   Habilita las APIs "Gmail API" y "Google Sheets API".
    *   Ve a "APIs y servicios" > "Pantalla de consentimiento de OAuth". Configúrala como "Externa" y añade tu email en la sección "Usuarios de prueba". **No necesitas enviar la app a verificación para uso personal.**
    *   Ve a "APIs y servicios" > "Credenciales". Crea un "ID de cliente de OAuth", selecciona "Aplicación de escritorio".
    *   **Descarga el archivo JSON** de credenciales y **renómbralo a `credentials.json`**.
    *   **¡IMPORTANTE! Coloca el archivo `credentials.json` en la carpeta raíz del proyecto.** Este archivo está incluido en `.gitignore` y **NO DEBE SER SUBIDO A GITHUB**.

5.  **Configurar el Script (`procesar_consumos.py`):**
    *   Abre `procesar_consumos.py` y revisa/modifica las constantes en la sección `--- CONFIGURACIÓN ---` si es necesario:
        *   `SPREADSHEET_ID`: El ID de tu Google Sheet (lo sacas de la URL).
        *   `SHEET_RANGE_NAME`: El nombre exacto de la pestaña donde quieres añadir los datos (ej: `'Cuentas'`).
        *   `GMAIL_LABEL_TO_SEARCH`: El nombre de la etiqueta en Gmail (formato `padre-hijo` si es anidada, ej: `'tarjetas-consumos-tarjeta'`).
        *   `PROCESSED_LABEL_NAME`: Nombre de la etiqueta que se añadirá a los correos procesados (ej: `'Procesado'`).

## Ejecución

1.  **Primera ejecución (Autorización):**
    *   Desde la terminal (con el entorno virtual activado), ejecuta:
        ```bash
        python procesar_consumos.py
        ```
    *   Se abrirá una ventana del navegador pidiéndote que inicies sesión con tu cuenta de Google y autorices a la aplicación a acceder a Gmail y Sheets. Concede los permisos.
    *   Esto creará un archivo `token.json` en la carpeta. Este archivo también está en `.gitignore` y **NO DEBE SER SUBIDO A GITHUB**.

2.  **Ejecuciones posteriores:**
    *   Simplemente ejecuta `python procesar_consumos.py` de nuevo. Usará el `token.json` para autenticarse sin pedirte permiso cada vez (a menos que el token expire o cambies los `SCOPES`).

## Automatización

Puedes programar la ejecución automática de este script usando:
*   `cron` en Linux o macOS.
*   El Programador de tareas en Windows.

## Seguridad

**¡NUNCA subas los archivos `credentials.json` o `token.json` a GitHub u otros repositorios públicos!** Contienen información sensible que podría dar acceso a tu cuenta. El archivo `.gitignore` está configurado para prevenir esto, pero siempre verifica antes de hacer commit.