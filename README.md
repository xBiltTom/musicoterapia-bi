# Musicoterapia BI

Aplicación web para explorar indicadores descriptivos de musicoterapia en los datos del proyecto Alzheimer. La fuente es la base **transaccional** `BD_Musicoterapia_Alzheimer` en SQL Server.

## Estado actual

- **Fase 1 completada como primera versión funcional:** API FastAPI, interfaz React y consultas SQL de K1, K2 y K3 sobre tablas transaccionales.
- **FR01–FR03:** consulta de pacientes seudonimizados, su perfil clínico por rol y el diario de sesiones con la música que consta en la base.
- **FR04:** consulta de las sesiones y minutos de cada paciente por semana. K4 requiere fichas semanales de vigencia y cobertura.
- Filtros por escenario de datos y fechas. `HIBRIDO` y `SINTETICO_IA` se consultan por separado.
- La API consulta `BD_Musicoterapia_Alzheimer` en solo lectura y valida las cuentas y permisos existentes en `usuario_sistema`.
- La base cargada en `localhost\SQLEXPRESS` es la fuente de datos. Los scripts en `database/` quedan como referencias del diseño y para bases de prueba independientes.

## Plan de implementación por fases

| Fase | Entregable | Estado |
| --- | --- | --- |
| 1. Base funcional | React + Vite + TypeScript, FastAPI, consultas de solo lectura a SQL Server, filtros y K1–K3 con consultas visibles en código. | Primera versión completada y verificada localmente. |
| 2. Reportes transaccionales | RP01 y RP02 con detalles por paciente/periodo, trazabilidad de denominadores, filtros válidos por indicador y exportación sencilla. | Pendiente. |
| 3. Resto de indicadores | FR04 semanal y K4 con denominador verificable; luego K5–K7 y RP03–RP04. No usar el antiguo `estado_seguimiento` global como sustituto. | FR04 implementado. K4 queda incompleto hasta registrar y confirmar todas las fichas de cada semana; otros indicadores pendientes. |
| 4. Interpretación asistida por IA | Explicaciones de agregados y límites de lectura, sin entrenar modelos predictivos ni emitir diagnósticos clínicos automáticos. | Pendiente. |
| 5. ETL y data mart | Diseñar modelo dimensional, construir carga y reconciliar resultados con las consultas transaccionales. La aplicación cambiará de fuente después de validar esa carga. | Fuera del alcance de esta etapa. |
| 6. Despliegue y entrega | Empaquetar interfaz y API, configurar conexión y respaldos de SQL Server, documentar instalación y evidencia de los indicadores. | Pendiente. |

La herramienta de la plataforma exigida por la asignatura debe confirmarse con la lista marcada con asterisco. KNIME es la opción prevista para la etapa ETL si cumple ese requisito. ECharts se usa para las visualizaciones en navegador y móvil.

## Arquitectura de esta etapa

```text
React + Vite + ECharts  →  FastAPI (/api)  →  SQL Server transaccional
```

La interfaz usa el proxy de Vite durante el desarrollo. Al compilarla, FastAPI puede servir `frontend/dist` desde el mismo origen, de modo que el navegador pueda usar la misma cookie de sesión para la interfaz y la API.

## Iniciar en Windows

Requisitos para este equipo: Python 3.12, Node.js, la instancia `localhost\SQLEXPRESS` con `BD_Musicoterapia_Alzheimer` y **ODBC Driver 17 for SQL Server**. La aplicación usa el puerto TCP local `127.0.0.1:1433` de esa instancia.

El valor predeterminado de `APP_SOLO_LECTURA` es `true`. La conexión de escritura también comprueba el nombre de la base y rechaza `BD_Musicoterapia_Alzheimer`. Para una prueba de registro se requiere una base independiente.

1. Copiar `.env.example` como `.env`. Ajustar `SERVER`, autenticación y certificado si el SQL Server usa otra configuración. La conexión predeterminada usa la cuenta de Windows que ejecuta la API.
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

## Acceso al sistema

Para ingresar, usar el `username` y la contraseña de una cuenta activa de `usuario_sistema`. La aplicación valida hashes Argon2 y bcrypt.

El tablero combina RP01 y RP02 y requiere ambos permisos de lectura con alcance global. FR04 es de lectura para quienes tienen acceso global a RP03. Las fichas y el diario muestran los datos permitidos por el rol de la cuenta.

En modo de solo lectura, la sesión dura hasta ocho horas y se conserva en memoria de la API. El perfil y sus permisos se revalidan en SQL Server cada dos minutos cuando hay actividad. Cerrar sesión o reiniciar el proceso la invalida. Para servir la aplicación por HTTPS, definir `AUTH_COOKIE_SECURE=true`. La interfaz y la API comparten origen con el proxy de Vite o al servir la compilación desde FastAPI.

La cuenta de SQL Server de la API necesita permisos de lectura. La configuración de conexión se guarda en `.env`, que está ignorado por Git.

## Fichas operativas

- **Pacientes (FR01).** Consulta de código, escenario y fechas del programa. El rol clínico también consulta la última visita, su diagnóstico y los medicamentos vinculados.
- **Sesiones (FR02 y FR03).** Consulta de asistencia, experiencia, respuesta y música asociada. El cuidador consulta las sesiones de las que figura como responsable.
- **Control semanal (FR04).** Consulta de sesiones y minutos por paciente y semana. Cuando la base carece de fichas semanales, la vista indica que K4 está pendiente de esa información.

La API de estas fichas se documenta en `/docs` bajo **FR01 · Pacientes** y **FR02 y FR03 · Sesiones**.

## Indicadores implementados

Las consultas están en [`backend/app/queries.py`](backend/app/queries.py). El escenario filtra mediante `paciente.escenario`; se selecciona uno a la vez.

| Indicador | Cálculo y denominador | Periodo |
| --- | --- | --- |
| K1 · Respuesta emocional positiva | `100 × POSITIVA / (POSITIVA + NEUTRA + NEGATIVA)` sobre `participacion_sesion.experiencia_sesion`. Excluye `NO_SABE` y vacíos. | Fecha de inicio de la sesión. |
| K2 · Reducción CMAI | Media de `CMAI inicial − CMAI seguimiento` por paciente con par válido; respondedor si la diferencia es ≥6. | Primera evaluación inicial anterior al fin del periodo y último seguimiento dentro del periodo. |
| K3 · Reducción CSDD | Media de `CSDD inicial − CSDD seguimiento` por paciente con par válido. Cruce del corte: basal `>10` y seguimiento `≤10`, dividido entre pares con basal `>10`. | Misma regla de fechas que K2. |

En K2 y K3 se usan resultados marcados `VALIDO`, dentro del rango de la escala y con seguimiento posterior a la evaluación inicial. Si falta un denominador válido, la API devuelve `null` y la interfaz muestra `—`. Los indicadores describen cambios observados.

## Fuente y decisiones de datos

- Informe de proyecto: `Informe_Inteligencia_de_Negocios_Alzheimer (2).docx`, secciones 4.3–4.7. El informe define siete KPI y cuatro reportes; esta fase implementa los tres primeros.
- `paciente.estado_seguimiento` refleja un estado general. La vigencia semanal de K4 se obtiene de FR04.
- FR04 usa una fila por paciente, semana ISO y programa. El campo `en_intervencion` representa esa semana; `cobertura_registro` distingue `COMPLETA`, `CERO_CONFIRMADO` e `INSUFICIENTE`. No se rellenaron filas históricas automáticamente.
- Los pacientes `HIBRIDO` y `SINTETICO_IA` tienen perfiles de resultados distintos. La interfaz impide mezclarlos en una sola tasa.
- La carpeta `database/data/` se ignora conforme a la decisión del equipo.

## API inicial

- `GET /api/salud`: verifica la conexión, el nombre de la base y el modo de acceso.
- `POST /api/auth/login`: recibe `usuario` y `contrasena` como JSON y abre una sesión con cookie.
- `GET /api/auth/sesion`: devuelve el perfil y los permisos de la sesión vigente.
- `POST /api/auth/logout`: invalida la sesión y borra su cookie. Enviar `Content-Type: application/json`.
- `GET /api/escenarios`: escenarios disponibles y número de pacientes.
- `GET /api/pacientes?escenario=HIBRIDO&buscar=&pagina=1`: pacientes ordenados por código, 25 por página, con el total que coincide con el escenario y el prefijo. En solo lectura, la API pagina una copia temporal de SQL Server en memoria. Se intenta renovar después de cinco minutos cuando hay actividad y se señala cuándo se muestra la última lectura disponible.
- `GET /api/tablero?escenario=HIBRIDO&desde=2022-01-01&hasta=2024-12-31`: K1–K3 y serie mensual de K1.
- En solo lectura se precalcula el periodo predeterminado de cada escenario y se guardan en memoria los agregados de hasta 12 pares de escenario y periodo. Después de cinco minutos se intenta actualizar los agregados consultados. Si SQL Server agota el tiempo de espera, se muestra la última lectura disponible para ese filtro.
- `GET /api/fr04/pacientes?escenario=HIBRIDO&semana_inicio=2024-10-28&buscar=...`: buscar pacientes candidatos a una ficha semanal.
- `GET /api/fr04/responsables`: devuelve el terapeuta autorizado de la sesión actual.
- `GET /api/fr04/ficha?escenario=HIBRIDO&semana_inicio=2024-10-28&codigo_paciente=...`: vigencia, cobertura, sesiones y minutos de un paciente.
- `GET /api/fr04/resumen?escenario=HIBRIDO&semana_inicio=2024-10-28`: avance semanal y K4 cuando sea calculable.

La API responde con error de validación si el intervalo está invertido o el escenario no existe. Las consultas usan parámetros SQL, sin interpolar valores recibidos del navegador.

## Regla FR04 y K4

El informe exige registrar **cada paciente activo en el programa durante la semana**, aunque no haya sesiones. La fecha de ingreso/salida del programa identifica candidatos a completar FR04, pero **no demuestra** que estuvieran en intervención. Esa vigencia se confirma en la ficha. El programa actual es `MUSICOTERAPIA`.

La ficha toma sesiones y minutos de `participacion_sesion` y `sesion_musical`. Cuenta participaciones `COMPLETA` o `INTERRUMPIDA` con duración positiva registrada; los minutos se calculan desde la hora de ingreso y salida del paciente. Los datos faltantes dejan la clasificación indeterminada. `CERO_CONFIRMADO` exige ausencia verificada de sesiones realizadas. Cumple la dosis quien realizó **al menos 3 sesiones y 30 minutos** en la semana.

**K4 = 100 × pacientes que cumplen / pacientes en intervención de esa semana.** La API devuelve `null` mientras haya fichas pendientes, cobertura insuficiente, horas inválidas o ningún paciente en intervención; muestra por separado las cantidades `CUMPLE`, `NO_CUMPLE`, `INDETERMINADA` y `FUERA`. Esto impide tratar las semanas sin datos como semanas con cero sesiones. Los datos históricos no se completarán con suposiciones: requieren reconstrucción y validación documentadas.

## Verificación realizada

- La compilación de React finalizó correctamente con `npm run build`.
- La API respondió por HTTP en `/api/salud` y `/api/tablero`; la interfaz compilada respondió en `/`.
- Para el periodo completo, `HIBRIDO` produjo K1 = 36,81 %, K2 = 1,45 y K3 = 1,51 puntos. `SINTETICO_IA` produjo K1 = 83,70 %, K2 = 13,52 y K3 = 8,97 puntos. Estos valores confirman que el filtro no mezcla escenarios.
- En la base definitiva se validan las consultas de pacientes, sesiones, tablero y control semanal con los permisos de cada rol. K4 requiere que exista el control semanal en la fuente.
