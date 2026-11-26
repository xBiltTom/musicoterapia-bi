# Musicoterapia BI

Aplicación web para explorar indicadores descriptivos de musicoterapia en pacientes con Alzheimer de un único centro. El trabajo parte de la base **transaccional** `BD_Musicoterapia_Alzheimer` en SQL Server. En esta etapa no hay ETL ni data mart.

## Estado actual

- **Fase 1 completada como primera versión funcional:** API FastAPI, interfaz React y consultas SQL de K1, K2 y K3 sobre tablas transaccionales.
- **FR04 implementado:** ficha semanal por paciente para confirmar vigencia y cobertura. K4 solo se calcula cuando el registro de la semana está completo.
- Filtros por escenario de datos y fechas. `HIBRIDO` y `SINTETICO_IA` se consultan por separado.
- El tablero K1–K3 consulta sin modificar datos. FR04 es el único módulo actual que registra información nueva en SQL Server.
- `database/schema.sql` es un volcado anterior y **no** representa los cambios recientes de la base. La fuente transaccional acordada es [`BD_Musicoterapia_Alzheimer.sql` en Drive](https://drive.google.com/file/d/1CWhF20zth-TU0raXBjLCyxlQHUKFx6Tt/view), copiada en [`database/BD_Musicoterapia_Alzheimer.sql`](database/BD_Musicoterapia_Alzheimer.sql). La base adjunta en SSMS tiene algunas columnas distintas de ese script; usar la migración incremental para actualizarla. No ejecutar el script completo sobre la base adjunta: contiene `DROP DATABASE`.

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

La interfaz usa el proxy de Vite durante el desarrollo. Al compilarla, FastAPI puede servir `frontend/dist` desde el mismo origen; así la demo puede ejecutarse en el equipo que ya tiene SQL Server. La aplicación solo escribe en `control_semanal_intervencion` al guardar FR04. La tabla se crea mediante una migración explícita.

## Iniciar en Windows

Requisitos: Python 3.12, Node.js, SQL Server con `BD_Musicoterapia_Alzheimer` accesible y **ODBC Driver 18 for SQL Server**.

Antes de usar FR04, aplicar una vez [`database/migrations/001_fr04_control_semanal.sql`](database/migrations/001_fr04_control_semanal.sql) en SSMS sobre `BD_Musicoterapia_Alzheimer`. La migración es repetible y no asigna estados históricos.

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

La cuenta de SQL Server usada por la API necesita `SELECT` en las tablas consultadas y `INSERT`/`UPDATE` en `control_semanal_intervencion` para guardar FR04. El responsable de la ficha debe existir en `usuario_sistema` como terapeuta activo. La edición FR04 está pensada para la demo local; antes de exponerla públicamente hay que implementar autenticación y permisos por rol. No guardar credenciales en Git; `.env` está ignorado.

## Indicadores implementados

Las consultas están en [`backend/app/queries.py`](backend/app/queries.py). El escenario filtra mediante `paciente.escenario`; se selecciona uno a la vez.

| Indicador | Cálculo y denominador | Periodo |
| --- | --- | --- |
| K1 · Respuesta emocional positiva | `100 × POSITIVA / (POSITIVA + NEUTRA + NEGATIVA)` sobre `participacion_sesion.experiencia_sesion`. Excluye `NO_SABE` y vacíos. | Fecha de inicio de la sesión. |
| K2 · Reducción CMAI | Media de `CMAI inicial − CMAI seguimiento` por paciente con par válido; respondedor si la diferencia es ≥6. | Primera evaluación inicial anterior al fin del periodo y último seguimiento dentro del periodo. |
| K3 · Reducción CSDD | Media de `CSDD inicial − CSDD seguimiento` por paciente con par válido. Cruce del corte: basal `>10` y seguimiento `≤10`, dividido entre pares con basal `>10`. | Misma regla de fechas que K2. |

En K2 y K3 el par requiere que el seguimiento sea posterior a la evaluación inicial. Los valores faltantes o fuera de los rangos de la escala se excluyen. Si no hay denominador válido, la API devuelve `null` y la interfaz muestra `—`. Estos indicadores expresan **cambios observados**, no una atribución causal al tratamiento.

## Fuente y decisiones de datos

- Informe de proyecto: `Informe_Inteligencia_de_Negocios_Alzheimer (2).docx`, secciones 4.3–4.7. El informe define siete KPI y cuatro reportes; esta fase implementa los tres primeros.
- Todos los registros de `visita_clinica` quedaron asignados al único centro elegido anteriormente. Esa reasignación es una decisión del proyecto y debe declararse al presentar resultados históricos.
- `paciente.estado_seguimiento` fue eliminado porque no expresaba estado semanal de intervención. `usuario_sistema.activo` tiene otra finalidad y permanece en la base.
- FR04 usa una fila por paciente, semana ISO y programa. El campo `en_intervencion` representa esa semana; `cobertura_registro` distingue `COMPLETA`, `CERO_CONFIRMADO` e `INSUFICIENTE`. No se rellenaron filas históricas automáticamente.
- Los pacientes `HIBRIDO` y `SINTETICO_IA` tienen perfiles de resultados distintos. La interfaz impide mezclarlos en una sola tasa.
- La carpeta `database/data/` se ignora conforme a la decisión del equipo.

## API inicial

- `GET /api/salud`: verifica conexión a SQL Server.
- `GET /api/escenarios`: escenarios disponibles y número de pacientes.
- `GET /api/tablero?escenario=HIBRIDO&desde=2022-01-01&hasta=2024-12-31`: K1–K3 y serie mensual de K1.
- `GET /api/fr04/pacientes?escenario=HIBRIDO&semana_inicio=2024-10-28&buscar=...`: buscar pacientes candidatos a una ficha semanal.
- `GET /api/fr04/responsables`: terapeutas activos que pueden figurar como responsables de FR04.
- `GET /api/fr04/ficha?escenario=HIBRIDO&semana_inicio=2024-10-28&codigo_paciente=...`: vigencia, cobertura, sesiones y minutos de un paciente.
- `PUT /api/fr04/ficha`: registrar o corregir una ficha FR04.
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
- La migración FR04 creó la tabla y sus claves foráneas en la base local. La búsqueda, la ficha, el resumen y los terapeutas activos respondieron por HTTP.
- Una ficha de prueba con 3 sesiones y 68 minutos se validó mediante inserción y actualización con **rollback**; no quedó ningún registro inventado. Para la semana del 28/10/2024, K4 permanece vacío porque faltan 12 651 fichas `HIBRIDO`.
