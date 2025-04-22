# Automatización de Registro de Consumos y Alertas de Presupuesto

Este proyecto automatiza el seguimiento de gastos de tarjetas de crédito personales, extrayendo datos de correos electrónicos y registrándolos en Google Sheets. Además, incluye un sistema de alertas por email basado en umbrales de presupuesto definidos.

El sistema consta de dos componentes principales:
1.  Un **script Python** (`procesar_consumos.py`) que se ejecuta periódicamente en un servidor para leer Gmail y escribir en Google Sheets.
2.  Un **Google Apps Script** vinculado a la hoja de cálculo que revisa el presupuesto y envía alertas por correo.

Actualmente está configurado para leer correos de **BBVA Argentina** y **Naranja X**.

## Funcionalidades Principales

*   **Lectura Multi-Banco:** Extrae datos de correos de confirmación de compra.
*   **Registro en Google Sheets:** Guarda automáticamente Fecha, Banco, Comercio, Tarjeta y Monto en una hoja designada.
*   **Categorización Semi-Automática:** Asigna categorías a los gastos basándose en una hoja de mapeo personalizable (`MapeoComercios`), con opción de asignación manual.
*   **Dashboard Dinámico:** Una hoja de Google Sheets (`Dashboard`) muestra resúmenes mensuales (total y por categoría) y un seguimiento semanal del presupuesto.
*   **Alertas de Presupuesto:** Un script de Google Apps envía alertas por correo electrónico cuando el gasto acumulado en una categoría supera el 50% y el 80% del presupuesto mensual definido. Evita enviar alertas duplicadas en el mismo mes.
*   **Ejecución en Servidor:** Diseñado para ejecutarse automáticamente en un entorno Linux (ej. Ubuntu) usando `cron`.

## Prerrequisitos

*   **Entorno de Ejecución:** Un servidor o máquina virtual con **Ubuntu** (o una distribución Linux similar). Puede ser un contenedor LXC, una VM completa o bare metal. Se necesita acceso a la línea de comandos.
*   **Software en el Servidor:**
    *   Python 3.x
    *   `pip` (gestor de paquetes de Python)
    *   `python3-venv` (para crear entornos virtuales)
    *   `git` (para clonar el repositorio)
*   **Cuenta de Google:** Para Gmail y Google Sheets.
*   **Proyecto en Google Cloud Platform (GCP):**
    *   APIs **Gmail API** y **Google Sheets API** habilitadas.
*   **Gmail:**
    *   Una etiqueta específica donde lleguen los correos de consumo (ej: `Tarjetas/Consumos Tarjeta`).
*   **Google Sheets:**
    *   Una hoja de cálculo con las siguientes pestañas (los nombres deben coincidir exactamente con los usados en los scripts):
        *   `Cuentas`: Donde el script Python escribirá los datos (Columnas mínimas: Fecha, Banco, Comercio, Tarjeta, Monto, Categoria).
        *   `MapeoComercios`: Para la categorización automática (Columnas: Comercio, CategoriaAsignada).
        *   `Presupuesto`: Donde defines tu presupuesto mensual (Columnas: Categoria, PresupuestoMensual).
        *   `Dashboard`: Para visualizar resúmenes y seguimiento (se puebla con fórmulas).
        *   `EstadoAlertas`: Usada por el Apps Script para rastrear qué alertas ya se enviaron (Columnas: Categoria, MesAño, Alerta50Enviada, Alerta80Enviada).

## Configuración

Sigue estos pasos **primero en tu máquina local** para la configuración inicial de Google y **luego en tu servidor Ubuntu** para la ejecución automática.

### A. Configuración Inicial (Google Cloud y Credenciales - Hazlo en tu PC Local)

1.  **Crea Proyecto en GCP:** Ve a [Google Cloud Console](https://console.cloud.google.com/) y crea un nuevo proyecto.
2.  **Habilita APIs:** Dentro del proyecto, busca y habilita "Gmail API" y "Google Sheets API".
3.  **Configura Pantalla de Consentimiento OAuth:**
    *   Ve a "APIs y servicios" > "Pantalla de consentimiento de OAuth".
    *   Selecciona "Externo" (User Type).
    *   Completa la información básica (nombre de la app, correo de asistencia).
    *   **Importante:** En "Usuarios de prueba", haz clic en "+ ADD USERS" y **añade tu propia dirección de correo electrónico**. Guarda. **No necesitas enviar la app a verificación** para tu uso personal.
4.  **Crea Credenciales:**
    *   Ve a "APIs y servicios" > "Credenciales".
    *   Haz clic en "+ CREAR CREDENCIALES" > "ID de cliente de OAuth".
    *   Selecciona **"Aplicación de escritorio"** como tipo de aplicación. Dale un nombre.
    *   Haz clic en "CREAR".
    *   Se mostrará tu ID de cliente y secreto. Haz clic en el botón **"DESCARGAR JSON"**.
    *   **Renombra el archivo descargado a `credentials.json`**. Este archivo es **SECRETO**.

### B. Configuración del Script Python (En el Servidor Ubuntu)

1.  **Conéctate al Servidor:** Accede a tu servidor Ubuntu vía SSH o consola.
2.  **Instala Software Necesario:**
    ```bash
    sudo apt update
    sudo apt install -y python3 python3-pip python3-venv git
    ```
3.  **Clona el Repositorio:**
    ```bash
    git clone https://github.com/leono81/finanzas.git
    cd finanzas
    ```
4.  **Copia `credentials.json` al Servidor:** Transfiere de forma segura el archivo `credentials.json` que descargaste en el paso A.4 a la carpeta `finanzas` en tu servidor (puedes usar `scp`, FileZilla, copiar/pegar en nano, etc.). **Asegúrate de que este archivo esté listado en tu `.gitignore` local para no subirlo accidentalmente a GitHub.**
5.  **Crea y Activa Entorno Virtual:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
    *(Verás `(venv)` al inicio de tu prompt)*.
6.  **Instala Dependencias:**
    ```bash
    pip install -r requirements.txt
    ```
7.  **Configura el Script (`procesar_consumos.py`):**
    *   Abre el script con un editor (ej: `nano procesar_consumos.py`).
    *   Revisa y ajusta las **constantes** en la sección `--- CONFIGURACIÓN ---` para que coincidan con tu configuración:
        *   `SPREADSHEET_ID`: El ID largo que aparece en la URL de tu Google Sheet.
        *   `SHEET_RANGE_NAME` (para Cuentas): `'Cuentas'` (o el nombre de tu hoja principal de gastos).
        *   `GMAIL_LABEL_TO_SEARCH`: La etiqueta de Gmail, usando formato `padre-hijo` si es anidada (ej: `'tarjetas-consumos-tarjeta'`).
        *   `PROCESSED_LABEL_NAME`: `'Procesado'` (o el nombre que prefieras).
    *   Guarda los cambios (`Ctrl+O`, `Enter`, `Ctrl+X` en nano).
8.  **Autorización Inicial (Flujo de Consola):**
    *   Asegúrate de que `token.json` **no** exista (`rm token.json` si existe).
    *   Ejecuta el script por primera vez:
        ```bash
        python procesar_consumos.py
        ```
    *   El script imprimirá una URL. **Copia** esta URL completa.
    *   **Pega** la URL en el navegador de tu **máquina local**.
    *   Inicia sesión con tu cuenta de Google y **autoriza** los permisos solicitados.
    *   Google te mostrará un **código de autorización**. **Copia** este código.
    *   **Pega** el código de vuelta en la **terminal del servidor** donde el script está esperando y presiona Enter.
    *   El script debería autenticarse y crear el archivo `token.json`. Este archivo también es **SECRETO** y debe estar en `.gitignore`. Las ejecuciones futuras usarán este token.

### C. Configuración del Google Apps Script (Alertas - Hazlo desde tu PC)

1.  **Abre tu Google Sheet.**
2.  Ve a `Extensiones` > `Apps Script`.
3.  **Nombra el Proyecto:** Dale un nombre como "Alertas Presupuesto".
4.  **Borra el Contenido:** Elimina cualquier código de ejemplo (`myFunction`).
5.  **Copia y Pega:** Copia **todo** el código del script de alertas proporcionado anteriormente y pégalo en el editor.
6.  **Configura las Constantes del Apps Script:** Revisa y ajusta las constantes al principio del script de Apps Script:
    *   `EMAIL_DESTINO`: Tu dirección de correo.
    *   `HOJA_DASHBOARD`, `HOJA_ALERTAS`, `HOJA_PRESUPUESTO`: Asegúrate de que los nombres coincidan *exactamente* con tus pestañas.
    *   `COL_..._NUM`: Verifica que los números de columna correspondan a tu diseño en el Dashboard (M=13, R=18 por defecto) y en EstadoAlertas (A=1, B=2, C=3, D=4 por defecto).
    *   `FILA_INICIO_DATOS_DASH`: La fila donde empiezan los datos de categoría en la tabla de seguimiento del Dashboard (la ajustamos a `4`).
7.  **Guarda el Script:** Clic en el icono de guardar (disquete).
8.  **Configura los Activadores (Triggers):**
    *   En el panel izquierdo del editor de Apps Script, haz clic en el icono de reloj ("Activadores").
    *   Haz clic en "+ Añadir activador".
    *   **Activador Diario/Horario:**
        *   Función: `chequearPresupuestoYAlertar`
        *   Despliegue: `Principal`
        *   Fuente evento: `Basado en tiempo`
        *   Tipo de activador: `Temporizador diario` (elige hora) o `Temporizador por horas`.
        *   Notificación de errores: `Notificarme inmediatamente`.
        *   **Guardar**. Autoriza los permisos cuando se te soliciten (revisa la pantalla de "aplicación no verificada", haz clic en "Configuración avanzada" > "Ir a [Nombre script] (no seguro)" > "Permitir").
    *   **Activador Mensual:**
        *   Función: `resetearAlertasMensuales`
        *   Despliegue: `Principal`
        *   Fuente evento: `Basado en tiempo`
        *   Tipo de activador: `Temporizador mensual`
        *   Día del mes: `Día 1 del mes`
        *   Hora: `Medianoche a 1 a. m.` (o similar).
        *   Notificación de errores: `Notificarme inmediatamente`.
        *   **Guardar**.

## Ejecución Automática (Python Script en Servidor Ubuntu)

Usa `cron` para ejecutar el script Python periódicamente.

1.  **Conéctate al Servidor Ubuntu.**
2.  **Abre el editor de crontab:**
    ```bash
    crontab -e
    ```
    (Elige un editor como `nano` si te pregunta).
3.  **Añade la línea de tarea**, reemplazando `/ruta/absoluta/a` con la ruta real donde clonaste el repositorio (ej: `/root/finanzas`):
    ```crontab
    # Ejecutar script de finanzas cada hora (al minuto 0)
    0 * * * * /ruta/absoluta/a/finanzas/venv/bin/python /ruta/absoluta/a/finanzas/procesar_consumos.py >> /ruta/absoluta/a/finanzas/consumos.log 2>&1
    ```
    *   `0 * * * *`: Ejecuta cada hora, a los 0 minutos. Cambia si prefieres otra frecuencia (ej: `*/30 * * * *` para cada 30 mins, `5 3 * * *` para las 3:05 AM diarias).
    *   Usa las rutas **absolutas** al ejecutable de Python en tu `venv` y al script.
    *   `>> ... consumos.log 2>&1`: Redirige toda la salida (normal y errores) al archivo de log.
4.  **Guarda y cierra** el editor (`Ctrl+O`, `Enter`, `Ctrl+X` en nano).

## Seguridad

**¡IMPORTANTE! Nunca subas los archivos `credentials.json` o `token.json` a GitHub ni los compartas.** Contienen información sensible que permite el acceso a tus cuentas. Asegúrate de que tu archivo `.gitignore` local los está excluyendo correctamente antes de hacer `git commit` y `git push`.