"""Formulario FR04 y seguimiento semanal sobre la base transaccional."""

from datetime import date, timedelta
from typing import Literal

import pyodbc
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .db import connection, fetch_all, fetch_one, write_connection


router = APIRouter(prefix="/api/fr04", tags=["FR04 · Adherencia semanal"])
PROGRAM = "MUSICOTERAPIA"

RESPONSIBLES = """
SELECT codigo_personal AS codigo_responsable, nombre_completo
FROM dbo.usuario_sistema
WHERE cargo_operativo = 'TERAPEUTA' AND activo = 1
ORDER BY codigo_personal
"""

PATIENTS = """
SELECT TOP (12) p.codigo_paciente
FROM dbo.paciente AS p
WHERE p.escenario = ?
  AND p.fecha_ingreso_programa < DATEADD(day, 7, CAST(? AS date))
  AND (p.fecha_salida_programa IS NULL OR p.fecha_salida_programa >= ?)
  AND (? = N'' OR CHARINDEX(?, p.codigo_paciente) = 1)
ORDER BY p.codigo_paciente
"""

PATIENT = """
SELECT p.id_paciente, p.codigo_paciente, p.escenario,
       p.fecha_ingreso_programa, p.fecha_salida_programa
FROM dbo.paciente AS p
WHERE p.codigo_paciente = ? AND p.escenario = ?
  AND p.fecha_ingreso_programa < DATEADD(day, 7, CAST(? AS date))
  AND (p.fecha_salida_programa IS NULL OR p.fecha_salida_programa >= ?)
"""

RECORD = """
SELECT en_intervencion, cobertura_registro, codigo_responsable,
       observaciones, fecha_actualizacion_utc
FROM dbo.control_semanal_intervencion
WHERE id_paciente = ? AND fecha_inicio_semana = ? AND codigo_programa = ?
"""

PATIENT_SESSIONS = """
SELECT s.codigo_sesion, s.fecha_hora_inicio_sesion,
       ps.estado_participacion,
       CASE WHEN ps.estado_participacion IN ('COMPLETA', 'INTERRUMPIDA')
             AND ps.fecha_hora_ingreso_paciente IS NOT NULL
             AND ps.fecha_hora_salida_paciente > ps.fecha_hora_ingreso_paciente
            THEN DATEDIFF(second, ps.fecha_hora_ingreso_paciente,
                ps.fecha_hora_salida_paciente)
            ELSE NULL END AS segundos_realizados
FROM dbo.participacion_sesion AS ps
JOIN dbo.sesion_musical AS s ON s.id_sesion_musical = ps.id_sesion_musical
WHERE ps.id_paciente = ?
  AND s.fecha_hora_inicio_sesion >= ?
  AND s.fecha_hora_inicio_sesion < DATEADD(day, 7, CAST(? AS date))
ORDER BY s.fecha_hora_inicio_sesion, s.id_sesion_musical
"""

CANDIDATES = """
SELECT COUNT_BIG(*) AS total FROM dbo.paciente
WHERE escenario = ?
  AND fecha_ingreso_programa < DATEADD(day, 7, CAST(? AS date))
  AND (fecha_salida_programa IS NULL OR fecha_salida_programa >= ?)
"""

WEEK_RECORDS = """
SELECT c.id_paciente, c.en_intervencion, c.cobertura_registro
FROM dbo.control_semanal_intervencion AS c
JOIN dbo.paciente AS p ON p.id_paciente = c.id_paciente
WHERE c.fecha_inicio_semana = ? AND c.codigo_programa = ? AND p.escenario = ?
  AND p.fecha_ingreso_programa < DATEADD(day, 7, CAST(? AS date))
  AND (p.fecha_salida_programa IS NULL OR p.fecha_salida_programa >= ?)
"""

WEEK_DOSE = """
SELECT ps.id_paciente,
       SUM(CASE WHEN ps.estado_participacion IN ('COMPLETA', 'INTERRUMPIDA')
                 AND ps.fecha_hora_ingreso_paciente IS NOT NULL
                 AND ps.fecha_hora_salida_paciente > ps.fecha_hora_ingreso_paciente
                THEN 1 ELSE 0 END) AS sesiones_realizadas,
       SUM(CASE WHEN ps.estado_participacion IN ('COMPLETA', 'INTERRUMPIDA')
                 AND ps.fecha_hora_ingreso_paciente IS NOT NULL
                 AND ps.fecha_hora_salida_paciente > ps.fecha_hora_ingreso_paciente
                THEN DATEDIFF(second, ps.fecha_hora_ingreso_paciente,
                     ps.fecha_hora_salida_paciente) ELSE 0 END) AS segundos,
       SUM(CASE WHEN ps.estado_participacion IN ('COMPLETA', 'INTERRUMPIDA')
                 AND (ps.fecha_hora_ingreso_paciente IS NULL
                   OR ps.fecha_hora_salida_paciente IS NULL
                   OR ps.fecha_hora_salida_paciente <= ps.fecha_hora_ingreso_paciente)
                THEN 1 ELSE 0 END) AS horas_invalidas
FROM dbo.participacion_sesion AS ps
JOIN dbo.sesion_musical AS s ON s.id_sesion_musical = ps.id_sesion_musical
JOIN dbo.paciente AS p ON p.id_paciente = ps.id_paciente
WHERE s.fecha_hora_inicio_sesion >= ?
  AND s.fecha_hora_inicio_sesion < DATEADD(day, 7, CAST(? AS date))
  AND p.escenario = ?
GROUP BY ps.id_paciente
"""


class FR04Input(BaseModel):
    escenario: Literal["HIBRIDO", "SINTETICO_IA"]
    codigo_paciente: str = Field(min_length=1, max_length=60)
    semana_inicio: date
    en_intervencion: bool
    cobertura_registro: Literal["COMPLETA", "INSUFICIENTE", "CERO_CONFIRMADO"] | None = None
    codigo_responsable: str = Field(min_length=1, max_length=50)
    observaciones: str | None = Field(default=None, max_length=500)


def check_week(week: date):
    if week.weekday() != 0:
        raise HTTPException(status_code=422, detail="La semana ISO debe comenzar un lunes")


def summarize_sessions(rows):
    sessions = 0
    seconds = 0
    invalid = 0
    for row in rows:
        if row["estado_participacion"] in ("COMPLETA", "INTERRUMPIDA"):
            duration = row["segundos_realizados"]
            if duration is None or duration <= 0:
                invalid += 1
            else:
                sessions += 1
                seconds += int(duration)
    return {"sesiones_realizadas": sessions, "minutos_realizados": round(seconds / 60, 2), "horas_invalidas": invalid}


def classification(record, dose):
    if record is None:
        return "PENDIENTE"
    if not record["en_intervencion"]:
        return "FUERA"
    if record["cobertura_registro"] == "INSUFICIENTE" or dose["horas_invalidas"]:
        return "INDETERMINADA"
    if record["cobertura_registro"] == "CERO_CONFIRMADO" and dose["sesiones_realizadas"]:
        return "INDETERMINADA"
    if record["cobertura_registro"] == "COMPLETA" and not dose["sesiones_realizadas"]:
        return "INDETERMINADA"
    if dose["sesiones_realizadas"] >= 3 and dose["minutos_realizados"] >= 30:
        return "CUMPLE"
    return "NO_CUMPLE"


def patient_for_week(conn, scenario, code, week):
    patient = fetch_one(conn, PATIENT, (code, scenario, week, week))
    if not patient:
        raise HTTPException(status_code=404, detail="Paciente no encontrado en ese escenario y semana del programa")
    return patient


def preview(conn, scenario, code, week):
    patient = patient_for_week(conn, scenario, code, week)
    rows = fetch_all(conn, PATIENT_SESSIONS, (patient["id_paciente"], week, week))
    dose = summarize_sessions(rows)
    record = fetch_one(conn, RECORD, (patient["id_paciente"], week, PROGRAM))
    return {
        "paciente": {"codigo_paciente": code, "escenario": scenario},
        "semana_inicio": week,
        "semana_fin": week + timedelta(days=6),
        "programa": PROGRAM,
        "registro": record,
        "dosis": dose,
        "clasificacion": classification(record, dose),
        "sesiones": [
            {"codigo_sesion": row["codigo_sesion"],
             "fecha_hora_inicio_sesion": row["fecha_hora_inicio_sesion"],
             "estado_participacion": row["estado_participacion"],
             "minutos_realizados": round(row["segundos_realizados"] / 60, 2) if row["segundos_realizados"] is not None else None}
            for row in rows
        ],
    }


@router.get("/pacientes")
def search_patients(
    escenario: Literal["HIBRIDO", "SINTETICO_IA"],
    semana_inicio: date,
    buscar: str = Query(default="", max_length=60),
):
    check_week(semana_inicio)
    try:
        with connection() as conn:
            return fetch_all(conn, PATIENTS, (escenario, semana_inicio, semana_inicio, buscar, buscar))
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar FR04") from exc


@router.get("/responsables")
def get_responsibles():
    try:
        with connection() as conn:
            return fetch_all(conn, RESPONSIBLES)
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar responsables") from exc


@router.get("/ficha")
def get_form(
    escenario: Literal["HIBRIDO", "SINTETICO_IA"],
    codigo_paciente: str = Query(min_length=1, max_length=60),
    semana_inicio: date = Query(),
):
    check_week(semana_inicio)
    try:
        with connection() as conn:
            return preview(conn, escenario, codigo_paciente, semana_inicio)
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar FR04") from exc


@router.get("/resumen")
def get_summary(escenario: Literal["HIBRIDO", "SINTETICO_IA"], semana_inicio: date):
    check_week(semana_inicio)
    try:
        with connection() as conn:
            candidates = int(fetch_one(conn, CANDIDATES, (escenario, semana_inicio, semana_inicio))["total"])
            records = fetch_all(conn, WEEK_RECORDS, (semana_inicio, PROGRAM, escenario, semana_inicio, semana_inicio))
            doses = {
                row["id_paciente"]: {
                    "sesiones_realizadas": int(row["sesiones_realizadas"] or 0),
                    "minutos_realizados": round(int(row["segundos"] or 0) / 60, 2),
                    "horas_invalidas": int(row["horas_invalidas"] or 0),
                }
                for row in fetch_all(conn, WEEK_DOSE, (semana_inicio, semana_inicio, escenario))
            }
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar FR04") from exc

    counts = {"FUERA": 0, "CUMPLE": 0, "NO_CUMPLE": 0, "INDETERMINADA": 0}
    empty_dose = {"sesiones_realizadas": 0, "minutos_realizados": 0, "horas_invalidas": 0}
    in_intervention = 0
    for record in records:
        if record["en_intervencion"]:
            in_intervention += 1
        counts[classification(record, doses.get(record["id_paciente"], empty_dose))] += 1
    pending = candidates - len(records)
    complete = pending == 0 and counts["INDETERMINADA"] == 0 and in_intervention > 0
    return {
        "escenario": escenario,
        "semana_inicio": semana_inicio,
        "candidatos_programa": candidates,
        "fichas_registradas": len(records),
        "fichas_pendientes": pending,
        "en_intervencion": in_intervention,
        "fuera_intervencion": counts["FUERA"],
        "cumple": counts["CUMPLE"],
        "no_cumple": counts["NO_CUMPLE"],
        "indeterminada": counts["INDETERMINADA"],
        "k4_tasa_adherencia": round(100 * counts["CUMPLE"] / in_intervention, 2) if complete else None,
        "estado_k4": "CALCULABLE" if complete else "INCOMPLETO",
    }


@router.put("/ficha")
def save_form(payload: FR04Input):
    check_week(payload.semana_inicio)
    code = payload.codigo_paciente.strip()
    responsible = payload.codigo_responsable.strip()
    if not code or not responsible:
        raise HTTPException(status_code=422, detail="Paciente y responsable son obligatorios")
    if payload.en_intervencion != (payload.cobertura_registro is not None):
        raise HTTPException(status_code=422, detail="La cobertura se registra solo para pacientes en intervención")

    try:
        with write_connection() as conn:
            if not fetch_one(conn, """SELECT id_usuario_sistema AS id FROM dbo.usuario_sistema
                                     WHERE codigo_personal = ? AND cargo_operativo = 'TERAPEUTA' AND activo = 1""", (responsible,)):
                raise HTTPException(status_code=422, detail="El responsable debe ser un terapeuta activo registrado")
            patient = patient_for_week(conn, payload.escenario, code, payload.semana_inicio)
            rows = fetch_all(conn, PATIENT_SESSIONS, (patient["id_paciente"], payload.semana_inicio, payload.semana_inicio))
            dose = summarize_sessions(rows)
            if payload.en_intervencion and payload.cobertura_registro == "CERO_CONFIRMADO" and (dose["sesiones_realizadas"] or dose["horas_invalidas"]):
                raise HTTPException(status_code=422, detail="Hay sesiones o registros sin hora válida; no puede confirmarse cero sesiones")
            if payload.en_intervencion and payload.cobertura_registro == "COMPLETA" and (dose["horas_invalidas"] or not dose["sesiones_realizadas"]):
                raise HTTPException(status_code=422, detail="Use cobertura insuficiente o cero sesiones confirmado")

            cursor = conn.cursor()
            try:
                cursor.execute(
                    """SELECT id_control_semanal FROM dbo.control_semanal_intervencion WITH (UPDLOCK, HOLDLOCK)
                       WHERE id_paciente = ? AND fecha_inicio_semana = ? AND codigo_programa = ?""",
                    patient["id_paciente"], payload.semana_inicio, PROGRAM,
                )
                existing = cursor.fetchone()
                if existing:
                    cursor.execute(
                        """UPDATE dbo.control_semanal_intervencion
                           SET en_intervencion = ?, cobertura_registro = ?, codigo_responsable = ?,
                               observaciones = ?, fecha_actualizacion_utc = SYSUTCDATETIME()
                           WHERE id_control_semanal = ?""",
                        payload.en_intervencion, payload.cobertura_registro, responsible,
                        payload.observaciones, existing[0],
                    )
                else:
                    cursor.execute(
                        """INSERT INTO dbo.control_semanal_intervencion
                           (id_paciente, fecha_inicio_semana, codigo_programa,
                            en_intervencion, cobertura_registro, codigo_responsable, observaciones)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        patient["id_paciente"], payload.semana_inicio, PROGRAM,
                        payload.en_intervencion, payload.cobertura_registro, responsible,
                        payload.observaciones,
                    )
            finally:
                cursor.close()
        with connection() as conn:
            return preview(conn, payload.escenario, code, payload.semana_inicio)
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail="No se pudo guardar FR04") from exc
