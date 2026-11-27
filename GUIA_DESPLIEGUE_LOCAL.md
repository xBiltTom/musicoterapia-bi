# Guía de despliegue local de Musicoterapia BI

La aplicación se ejecuta en Windows y se abre en el navegador. Puedes usar **SQLEXPRESS en este equipo** o ejecutar la aplicación localmente con sus bases en **Azure SQL**.

| Base | Para qué la usa la aplicación |
| --- | --- |
| Transaccional u OLTP | Valida cuentas y permisos. Consulta pacientes, perfiles, sesiones y música. |
| Datamart | Calcula K1 a K7, compara escenarios y devuelve el resumen semanal de FR04. La ficha individual de FR04 también consulta la OLTP. |

## 1. Preparar la aplicación

Necesitas **Python 3.12**, **Node.js 22.12 o superior de la rama 22** y una copia del proyecto que incluya los cambios de K1 a K7. Abre PowerShell en la carpeta donde están `README.md`, `backend` y `frontend`. En este equipo, usa esta ruta.

~~~powershell
Set-Location 'C:\Users\USERJSSV\Downloads\musicoterapia-bi'
python --version
node --version
~~~

Si `.venv` ya existe y usa Python 3.12, reutilízala. Si vas a crearla y `python --version` devuelve otra versión, usa la ruta al ejecutable de Python 3.12 para crearla. La compilación prepara los archivos que FastAPI servirá junto con la API.

~~~powershell
if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe --version
& .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm.cmd ci --prefix frontend
npm.cmd run build --prefix frontend
~~~

Si falla un comando, resuelve ese error antes de continuar. Al terminar la compilación debe existir `frontend\dist\index.html`.

## 2. Usar SQLEXPRESS

Instala **SQL Server Express 2022** y **ODBC Driver 17 for SQL Server** si aún faltan. Para comprobar la instancia e importar los scripts, usa `sqlcmd`. Esta instalación usa autenticación de Windows. La cuenta que ejecuta la API necesita acceso de lectura a ambas bases.

### Comprobar la instancia y las bases

En el equipo del proyecto, `SQLEXPRESS` ya escucha en `127.0.0.1:1433`. Comprueba el puerto y los nombres de las bases.

~~~powershell
Test-NetConnection 127.0.0.1 -Port 1433
sqlcmd -S tcp:127.0.0.1,1433 -E -b -Q "SELECT name, compatibility_level FROM sys.databases WHERE name LIKE '%Musicoterapia%';"
~~~

Si la instancia usa otro puerto, colócalo en ambas cadenas de conexión. Para configurar un puerto fijo, abre **SQL Server Configuration Manager → Configuración de red de SQL Server → Protocolos de SQLEXPRESS → TCP/IP**. Habilita TCP/IP. Con **Escuchar todo** activo, deja vacío **Puertos dinámicos TCP** y escribe el puerto en **IPAll → Puerto TCP**. Reinicia el servicio **SQL Server (SQLEXPRESS)**. [Propiedades de TCP/IP en SQL Server](https://learn.microsoft.com/en-us/sql/tools/configuration-manager/tcp-ip-properties-ip-addresses-tab)

La instalación comprobada tiene `BD_Musicoterapia_Alzheimer_20261127` y `Datamart_Musicoterapia_Alzheimer`. Si ya están cargadas, puedes continuar con la configuración de `.env`.

Para una instancia nueva, restaura los respaldos de las dos bases preparadas o usa el paquete **Scripts de generación**. Si usas el paquete, ejecuta `OLTP_01_Definicion.sql`, `OLTP_02_Poblacion-001.sql` y los scripts del Datamart en orden del 01 al 08. Usa `sqlcmd -S tcp:127.0.0.1,1433 -E -b -i "ruta-del-archivo.sql"` para el poblado de la OLTP, que pesa aproximadamente 3,3 GB. El paso 01 del Datamart redefine sus tablas. Ejecútalo sobre una instalación vacía o una reconstrucción planificada con respaldo.

- Los scripts del paquete crean la OLTP como `BD_Musicoterapia_Alzheimer`. Si conservas ese nombre, úsalo en `SQLSERVER_CONNECTION_STRING` y reemplaza `[BD_Musicoterapia_Alzheimer_20261127]` por `[BD_Musicoterapia_Alzheimer]` en una copia de `database/migrations/005_datamart_indicadores.sql`.
- Ejecuta la migración 005 **después de cargar los hechos**. Si restauras bases que ya la incluyen, puedes continuar. El Datamart requiere compatibilidad 160 o superior porque los scripts usan `GENERATE_SERIES`. [Requisito de GENERATE_SERIES](https://learn.microsoft.com/en-us/sql/t-sql/functions/generate-series-transact-sql)

### Configurar el archivo .env

Desde la raíz del proyecto:

~~~powershell
if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
}
notepad .env
~~~

Revisa estos valores. Si cambió el nombre o puerto, ajusta la cadena correspondiente.

~~~dotenv
SQLSERVER_CONNECTION_STRING=DRIVER={ODBC Driver 17 for SQL Server};SERVER=tcp:127.0.0.1,1433;DATABASE=BD_Musicoterapia_Alzheimer_20261127;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes
SQLSERVER_DATAMART_CONNECTION_STRING=DRIVER={ODBC Driver 17 for SQL Server};SERVER=tcp:127.0.0.1,1433;DATABASE=Datamart_Musicoterapia_Alzheimer;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes
APP_SOLO_LECTURA=true
AUTH_COOKIE_SECURE=false
~~~

Para usar SQLEXPRESS, las variables `AZURE_SQL_OLTP_URL` y `AZURE_SQL_DATAMART_URL` deben estar ausentes en `.env` y en la sesión de PowerShell que ejecuta la API. Continúa en [Arrancar y comprobar](#4-arrancar-y-comprobar).

## 3. Usar la nueva conexión de Azure SQL

La aplicación seguirá en tu equipo y consultará Azure por TLS. Confirma estos puntos:

- **Conexión.** Necesitas el nombre completo del servidor `servidor.database.windows.net`, los nombres de la OLTP y del Datamart, y credenciales SQL de aplicación. Ambos nombres pueden coincidir si esa base contiene los dos modelos bajo `dbo`.
- **Datos.** La OLTP debe incluir las tablas operativas, roles y cuentas. El Datamart debe tener datos en `DimPaciente`, `DimTiempo`, `DimCuidador`, `HechoAdherencia`, `HechoRespuestaDiaria`, `HechoPuntajeValido` y `HechoTurnoDiario`. Si partes de los scripts locales, adapta sus referencias entre bases antes de ejecutar la carga en Azure. [Migración de bases a Azure SQL Database](https://learn.microsoft.com/en-us/data-migration/sql-server/database/assessment-rules)
- **Permisos.** La cuenta SQL de aplicación necesita lectura en ambas bases. Para abrir y cerrar sesiones requiere también `SELECT`, `INSERT` y `DELETE` sobre `dbo.sesion_autenticacion` en la OLTP. Si falta esa tabla, el administrador ejecuta `database/migrations/002_autenticacion.sql` en la transaccional.
- **Red.** Si Azure usa acceso público, el administrador abre **Redes → Acceso público**, selecciona **Redes seleccionadas**, agrega la **IP pública del equipo** y guarda. Comprueba el puerto con `Test-NetConnection servidor.database.windows.net -Port 1433`. Prueba también el acceso a cada base con SSMS para confirmar que Azure acepta las credenciales desde el equipo. [Firewall de Azure SQL](https://learn.microsoft.com/en-us/azure/azure-sql/database/firewall-create-server-level-portal-quickstart?view=azuresql)

Pega este bloque en PowerShell. Te pedirá los datos de cada conexión y codificará los caracteres reservados de la contraseña. Si ambas conexiones apuntan a la misma base y usan la misma cuenta, ingresa los mismos datos dos veces.

~~~powershell
function Set-MusicoterapiaAzureConnection {
    param([string]$Variable)

    Write-Host "Configurando $Variable"
    $servidor = Read-Host 'Servidor SQL (solo el nombre, sin https://)'
    $base = [Uri]::EscapeDataString((Read-Host 'Nombre de la base'))
    $cuenta = Get-Credential -Message 'Usuario y contraseña de Azure SQL'
    if (-not $cuenta) { throw 'Configuración cancelada' }

    $usuario = [Uri]::EscapeDataString($cuenta.UserName)
    $clave = [Uri]::EscapeDataString($cuenta.GetNetworkCredential().Password)
    $url = "mssql://${usuario}:${clave}@${servidor}:1433/$base"
    [Environment]::SetEnvironmentVariable($Variable, $url, 'Process')
}

Set-MusicoterapiaAzureConnection AZURE_SQL_OLTP_URL
Set-MusicoterapiaAzureConnection AZURE_SQL_DATAMART_URL
~~~

Arranca la API **en esa misma ventana**. Las credenciales se conservan durante la sesión de PowerShell. Para probar el inicio de sesión en modo Azure, usa `http://localhost:8011/` en Edge o Chrome. La aplicación marca la cookie como `Secure` y estos navegadores permiten la excepción de `localhost` para la prueba local. [Atributo Secure de las cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie#secure)

Para volver a SQLEXPRESS, detén la API con **Ctrl+C**, cierra esa sesión de PowerShell y abre otra con la configuración local. Si guardaste las variables Azure en `.env`, quítalas también de ese archivo.

## 4. Arrancar y comprobar

Con una de las conexiones configurada, ejecuta desde la raíz:

~~~powershell
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8011
~~~

Mantén PowerShell abierto y sigue estas comprobaciones.

1. Abre [la comprobación de salud](http://localhost:8011/api/salud). Confirma que `estado` y `datamart.estado` muestran `ok`. Revisa los nombres en `base` y `datamart.base`. Usa esos campos para confirmar la conexión aunque la pantalla diga «Base local · Solo lectura».
2. Abre [Musicoterapia BI](http://localhost:8011/) e ingresa con una cuenta activa del **sistema** asignada por el centro. El usuario SQL se usa para conectar la API a la base.
3. En **Indicadores**, selecciona **Comparar escenarios**, **Pacientes elegibles** y el periodo del **01/01/2022 al 31/12/2024**. Con los permisos completos, debes ver K1 a K7.
4. Con acceso a **Control semanal**, elige **Híbrido**, **Pacientes elegibles** y el lunes **24/07/2023**. En los datos comprobados del proyecto, FR04 mostró **206 de 2 688 pacientes**, equivalente al **7,66 %**.

| Si aparece | Qué revisar |
| --- | --- |
| El navegador no abre la página | Revisa la salida de Uvicorn. Si el puerto 8011 está ocupado, usa otro puerto disponible y ajusta la URL. |
| Abre la API pero falta la pantalla | Ejecuta `npm.cmd run build --prefix frontend` y reinicia Uvicorn para que encuentre `frontend/dist`. |
| `/api/salud` devuelve 503 | Revisa la conexión transaccional. En SQLEXPRESS comprueba TCP y la cadena ODBC. En Azure verifica IP autorizada, servidor, base y credenciales SQL. |
| `datamart.estado` devuelve `no_disponible` | Revisa la segunda conexión y sus permisos de lectura. |
| El tablero muestra «Sin datos» o falla | Revisa los filtros, los permisos del rol y que el Datamart tenga los datos y tablas de la migración 005. |
| Usuario o contraseña incorrectos | Comprueba con el administrador que la cuenta de la aplicación esté activa en `dbo.usuario_sistema` y tenga una contraseña habilitada. |
| Azure responde pero el login no abre sesión | Comprueba `dbo.sesion_autenticacion` y sus permisos. Para la prueba en Windows usa `localhost` en Edge o Chrome. |

**Comprobado en este equipo:** SQLEXPRESS 2022, las dos bases disponibles y el endpoint `/api/salud` correcto en el puerto 8011. La prueba de Azure se puede realizar cuando tengas la nueva conexión.
