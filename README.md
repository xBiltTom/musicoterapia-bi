# Musicoterapia BI

Aplicación web para explorar indicadores descriptivos de musicoterapia en los datos del proyecto Alzheimer. Las fichas y cuentas se consultan en `BD_Musicoterapia_Alzheimer_20261127` y el tablero K1–K7 en `Datamart_Musicoterapia_Alzheimer`.

## Estado actual

- **Tablero K1–K7:** valores, denominadores y semáforos del informe. Permite comparar ambos escenarios y selecciona por defecto a los pacientes elegibles.
- **FR01–FR03:** consulta de pacientes seudonimizados, su perfil clínico por rol y el diario de sesiones con la música que consta en la base.
- **FR04:** adherencia semanal calculada a partir de FR03, con el detalle de las sesiones de cada paciente.
- La API consulta la OLTP nueva en solo lectura y valida las cuentas y permisos existentes en `usuario_sistema`.
- Ambas bases están en `localhost\SQLEXPRESS`.

## Plan de implementación por fases

| Fase | Entregable | Estado |
| --- | --- | --- |
| 1. Base funcional | React + Vite + TypeScript, FastAPI, consultas de solo lectura a SQL Server, filtros y K1–K3 con consultas visibles en código. | Primera versión completada y verificada localmente. |
| 2. Reportes transaccionales | RP01 y RP02 con detalles por paciente/periodo, trazabilidad de denominadores, filtros válidos por indicador y exportación sencilla. | Pendiente. |
| 3. Resto de indicadores | FR04 automático, adherencia, MMSE, latencia y reducción de episodios por turno. | K4–K7 disponibles en el tablero y FR04 semanal habilitado. |
| 4. Interpretación asistida por IA | Explicaciones de agregados y límites de lectura, sin entrenar modelos predictivos ni emitir diagnósticos clínicos automáticos. | Pendiente. |
| 5. ETL y Datamart | Cargar y reconciliar indicadores dimensionales. | Carga validada e integrada al tablero K1–K7. |
| 6. Despliegue y entrega | Empaquetar interfaz y API, configurar conexión y respaldos de SQL Server, documentar instalación y evidencia de los indicadores. | Configuración de Vercel incluida. La conexión depende del acceso a Azure SQL. |

La herramienta de la plataforma exigida por la asignatura debe confirmarse con la lista marcada con asterisco. KNIME es la opción prevista para la etapa ETL si cumple ese requisito. ECharts se usa para las visualizaciones en navegador y móvil.

## Arquitectura de esta etapa

```text
React + Vite + ECharts  →  FastAPI (/api)  →  OLTP para acceso y fichas
                                         →  Datamart para Indicadores
```

La interfaz usa el proxy de Vite durante el desarrollo. Al compilarla, FastAPI puede servir `frontend/dist` desde el mismo origen, de modo que el navegador pueda usar la misma cookie de sesión para la interfaz y la API.

## Iniciar en Windows

Requisitos para este equipo: Python 3.12, Node.js, las dos bases del proyecto en `localhost\SQLEXPRESS` y **ODBC Driver 17 for SQL Server**. La aplicación usa el puerto TCP local `127.0.0.1:1433` de esa instancia.

El valor predeterminado de `APP_SOLO_LECTURA` es `true`. La conexión de escritura exige una base de pruebas independiente de las bases del proyecto.

1. Copiar `.env.example` como `.env`. `SQLSERVER_CONNECTION_STRING` apunta a la OLTP y `SQLSERVER_DATAMART_CONNECTION_STRING` al Datamart. Las conexiones predeterminadas usan la cuenta de Windows que ejecuta la API.
2. Desde la raíz del repositorio:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload
   ```

3. En otra terminal:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

4. Abrir `http://localhost:5173`. La API tiene documentación en `http://localhost:8000/docs` y un control de conexión en `http://localhost:8000/api/salud`.

Para probar el formato de despliegue en el mismo equipo, ejecutar `npm run build` dentro de `frontend` y reiniciar la API. FastAPI servirá la interfaz compilada en `http://localhost:8000`.

Tras cargar las dimensiones y los hechos del Datamart, ejecutar [`005_datamart_indicadores.sql`](database/migrations/005_datamart_indicadores.sql) en SQLEXPRESS. La migración actualiza la dosis de K4 y refresca los agregados diarios y los puntajes que permiten calcular los indicadores para cada periodo.

## Desplegar en Vercel con Azure SQL

Desde la raíz del repositorio, `vercel deploy --prod` compila React y publica la interfaz y FastAPI en el mismo origen. Configurar estas variables sensibles en el proyecto de Vercel y volver a desplegar tras modificarlas.

| Variable | Base y permisos de la cuenta de la aplicación |
| --- | --- |
| `AZURE_SQL_OLTP_URL` | Lectura en las tablas de cuentas, roles, pacientes y sesiones. La cuenta también necesita leer, insertar y eliminar filas de `dbo.sesion_autenticacion`. |
| `AZURE_SQL_DATAMART_URL` | Lectura en las dimensiones y los hechos del tablero K1–K7. |

Las dos variables usan el formato `mssql://usuario:contraseña@servidor.database.windows.net:1433/base`. Codificar los caracteres reservados de usuario y contraseña como componentes de URL. Azure debe permitir la conexión desde la red de salida de Vercel. La API usa TLS y verifica el certificado del servidor.

Crear `dbo.sesion_autenticacion` en la base transaccional con [`002_autenticacion.sql`](database/migrations/002_autenticacion.sql) si la tabla aún no existe. Las sesiones se comparten entre instancias de la función y usan cookies HTTPS. Los módulos operativos funcionan en modo de solo lectura.

Las dos variables pueden apuntar a la misma base si contiene ambos modelos bajo `dbo`. El Datamart debe incluir las dimensiones y los hechos calculados de la versión final. Los scripts de carga locales que usan nombres de tres partes requieren adaptación para cargar el Datamart en Azure SQL Database.

Consultar `/api/salud` después del despliegue para verificar el acceso de la API a ambas bases. El inicio de sesión requiere que la base transaccional esté disponible.

## Acceso al sistema

Para ingresar, usar el `username` y la contraseña de una cuenta activa de `usuario_sistema`. La aplicación valida hashes Argon2 y bcrypt.

El tablero muestra los indicadores habilitados por los permisos independientes RP01–RP04. RP01 cubre K1 y K6, RP02 cubre K2, K3 y K5, RP03 cubre K4 y RP04 cubre K7. Para cuidadores de alcance propio, RP01 y RP04 se limitan a registros donde figuran como responsables. FR04 está disponible para roles con acceso global a RP03 o a la ficha semanal.

En modo local de solo lectura, la sesión dura hasta ocho horas y se conserva en memoria de la API. El perfil y sus permisos se revalidan en SQL Server cada dos minutos cuando hay actividad. Cerrar sesión o reiniciar el proceso la invalida. Para servir la aplicación local por HTTPS, definir `AUTH_COOKIE_SECURE=true`. La interfaz y la API comparten origen con el proxy de Vite o al servir la compilación desde FastAPI.

La cuenta de SQL Server de la API necesita permisos de lectura en ambas bases. La configuración de conexión se guarda en `.env`, que está ignorado por Git.

## Fichas operativas

- **Pacientes (FR01).** Consulta de código, escenario y fechas del programa. El rol clínico también consulta la última visita, su diagnóstico y los medicamentos vinculados.
- **Sesiones (FR02 y FR03).** Consulta de asistencia, experiencia, respuesta y música asociada. El cuidador consulta las sesiones de las que figura como responsable.
- **Control semanal (FR04).** Consulta de la tasa semanal y del detalle de participaciones completas o interrumpidas por paciente, con las horas de ingreso y salida.

La API de estas fichas se documenta en `/docs` bajo **FR01 · Pacientes** y **FR02 y FR03 · Sesiones**.

## Indicadores implementados

Las consultas están en [`backend/app/queries.py`](backend/app/queries.py). La población elegible aplica la marca `DimPaciente.Inclusion`, que combina diagnóstico de Alzheimer, primer CDR válido entre 0,5 y 2, y edad de 60 años o más en la primera visita.

| Indicador | Cálculo y denominador | Periodo |
| --- | --- | --- |
| K1 · Respuesta emocional positiva | Positivas ÷ (positivas + neutras + negativas), expresado como porcentaje. | Fecha de inicio de la sesión. |
| K2 · Reducción CMAI | Promedio del cambio basal − seguimiento por paciente, con porcentaje de respondedores con reducción de al menos 6 puntos. | Último seguimiento válido dentro del periodo y primer basal válido anterior. |
| K3 · Reducción CSDD | Promedio del cambio basal − seguimiento por paciente; cruce del corte de >10 a ≤10 entre pares con basal >10. | Misma regla que K2. |
| K4 · Adherencia | Paciente-semanas que cumplen la dosis ÷ paciente-semanas en intervención, expresado como porcentaje. | Semanas ISO completas que intersectan el periodo. |
| K5 · MMSE | Promedio del último MMSE válido de cada paciente. Se informa también la variación desde el primer MMSE válido del periodo si hay dos fechas distintas. | Fecha de evaluación dentro del periodo. |
| K6 · Latencia de respuesta | Promedio de minutos entre inicio de la música y primera respuesta positiva registrada. El porcentaje sin respuesta usa las observaciones con respuesta registrada o ausencia confirmada. | Fecha de inicio de la sesión. |
| K7 · Agitación por turno | Promedio por paciente de la tasa inicial menos la reciente. Cada tasa divide episodios por turnos observados con conteo válido. | Primer y último trimestre distinto con turnos válidos en el periodo. |

Cuando falta un denominador válido, la API devuelve `null` y la interfaz muestra «Sin datos». Los semáforos usan el valor antes del redondeo de pantalla.

## Fuente y decisiones de datos

- La hoja maestra define los KPI y los umbrales en las secciones 3.1 y 3.3. El anexo 4 define FR04 como un resumen calculado.
- `HIBRIDO` y `SINTETICO_IA` son escenarios de datos de prueba. La comparación aplica el mismo periodo y criterio de inclusión a cada escenario.
- La carpeta `database/data/` se ignora conforme a la decisión del equipo.

## API inicial

- `GET /api/salud` verifica las dos conexiones y devuelve el modo de acceso de la OLTP.
- `POST /api/auth/login`: recibe `usuario` y `contrasena` como JSON y abre una sesión con cookie.
- `GET /api/auth/sesion`: devuelve el perfil y los permisos de la sesión vigente.
- `POST /api/auth/logout`: invalida la sesión y borra su cookie. Enviar `Content-Type: application/json`.
- `GET /api/escenarios` devuelve los conteos totales y elegibles para perfiles de alcance global.
- `GET /api/pacientes?escenario=HIBRIDO&buscar=&pagina=1`: pacientes ordenados por código, 25 por página, con el total que coincide con el escenario y el prefijo. En solo lectura, la API pagina una copia temporal de SQL Server en memoria. Se intenta renovar después de cinco minutos cuando hay actividad y se señala cuándo se muestra la última lectura disponible.
- `GET /api/tablero?escenario=COMPARAR&desde=2022-01-01&hasta=2024-12-31&poblacion=incluidos` devuelve los KPI autorizados para los dos escenarios. Para una sola población, usar `HIBRIDO` o `SINTETICO_IA`.
- En solo lectura se guardan hasta 12 resultados por escenario, fechas, población y permisos. Después de cinco minutos se intenta actualizar el resultado.
- `GET /api/fr04/pacientes` busca por código dentro de quienes figuran en intervención para la semana y población.
- `GET /api/fr04/ficha` devuelve la dosis y el detalle de una persona en intervención en esa semana.
- `GET /api/fr04/resumen?escenario=HIBRIDO&semana_inicio=2023-07-24&poblacion=incluidos` devuelve K4 para la semana ISO.

La API responde con error de validación si el intervalo está invertido o el escenario no existe. Las consultas usan parámetros SQL, sin interpolar valores recibidos del navegador.

## Regla FR04 y K4

La vigencia de cada paciente va de la primera a la última semana ISO con una sesión realizada. Las semanas intermedias con cero sesiones cuentan como «No cumple».

La dosis se calcula con participaciones completas o interrumpidas. Cumple quien realiza al menos tres sesiones y acumula 1.800 segundos entre las horas registradas de ingreso y salida. FR04 muestra la dosis y las sesiones que la sustentan. El total del periodo en el tablero usa paciente-semanas como unidad.

## Verificación realizada

- La compilación de React finalizó correctamente con `npm run build`.
- La API respondió por HTTP en `/api/salud` y `/api/tablero`; la interfaz compilada respondió en `/`.
- En toda la población 2022–2024, K4 corregido da 64.433 de 710.378 paciente-semanas. En la semana del 24/07/2023, 607 de 6.289 pacientes cumplieron.
- El corte de MMSE al 31/12/2023 recupera 7.322 pacientes híbridos y 8.579 sintéticos con puntaje válido.
