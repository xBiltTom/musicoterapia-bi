"""Control semanal FR04 con la dosis calculada a partir de FR03."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import require_fr04, require_fr04_detail
from .db import DB_ERRORS, connection, datamart_connection, fetch_all, fetch_one
from .indicadores import Population, Scenario, read_adherence


router = APIRouter(prefix="/api/fr04", tags=["FR04 · Adherencia semanal"], dependencies=[Depends(require_fr04)])

PATIENTS = """
SELECT TOP (12) p.CodigoPaciente AS codigo_paciente
FROM dbo.HechoAdherencia h
JOIN dbo.DimPaciente p ON p.KeyPaciente=h.KeyPaciente
JOIN dbo.DimTiempo t ON t.KeyTiempo=h.KeyTiempo
WHERE p.Escenario=? AND (?=0 OR p.Inclusion=N'Incluido') AND t.idTiempo=?
  AND (?=N'' OR CHARINDEX(?,p.CodigoPaciente)=1)
ORDER BY p.CodigoPaciente
"""

PATIENT_WEEK = """
SELECT p.idPaciente AS id_paciente,p.CodigoPaciente AS codigo_paciente,
       h.PacientesQueCumplenDosis AS cumple,h.SesionesPorSemana AS sesiones
FROM dbo.HechoAdherencia h
JOIN dbo.DimPaciente p ON p.KeyPaciente=h.KeyPaciente
JOIN dbo.DimTiempo t ON t.KeyTiempo=h.KeyTiempo
WHERE p.Escenario=? AND (?=0 OR p.Inclusion=N'Incluido') AND t.idTiempo=? AND p.CodigoPaciente=?
"""

PATIENT_SESSIONS = """
SELECT s.codigo_sesion, s.fecha_hora_inicio_sesion, ps.estado_participacion,
       ps.fecha_hora_ingreso_paciente, ps.fecha_hora_salida_paciente,
       DATEDIFF(second,ps.fecha_hora_ingreso_paciente,ps.fecha_hora_salida_paciente) AS segundos
FROM dbo.participacion_sesion ps
JOIN dbo.sesion_musical s ON s.id_sesion_musical=ps.id_sesion_musical
WHERE ps.id_paciente=? AND s.fecha_hora_inicio_sesion>=? AND s.fecha_hora_inicio_sesion<?
  AND ps.estado_participacion IN ('COMPLETA','INTERRUMPIDA')
ORDER BY s.fecha_hora_inicio_sesion,s.id_sesion_musical
"""


def check_week(week: date):
    if week.weekday() != 0:
        raise HTTPException(status_code=422, detail="La semana ISO debe comenzar un lunes")
    if week > date.max - timedelta(days=7):
        raise HTTPException(status_code=422, detail="La semana excede el intervalo de fechas")


@router.get("/pacientes", dependencies=[Depends(require_fr04_detail)])
def patients(
    escenario: Scenario, semana_inicio: date, poblacion: Population = "incluidos",
    buscar: str = Query(default="", max_length=120),
):
    check_week(semana_inicio)
    prefix = buscar.strip()
    try:
        with datamart_connection() as conn:
            return fetch_all(conn, PATIENTS, (escenario, poblacion == "incluidos", semana_inicio, prefix, prefix))
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar el control semanal") from exc


@router.get("/resumen")
def summary(escenario: Scenario, semana_inicio: date, poblacion: Population = "incluidos"):
    check_week(semana_inicio)
    try:
        with datamart_connection() as conn:
            result = read_adherence(conn, escenario, poblacion, semana_inicio, semana_inicio)
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar la adherencia semanal") from exc
    return {
        "escenario": escenario, "poblacion": poblacion, "semana_inicio": semana_inicio,
        "en_intervencion": result["paciente_semanas"], "cumple": result["cumplen"],
        "no_cumple": result["paciente_semanas"] - result["cumplen"],
        "k4_tasa_adherencia": result["tasa_adherencia"], "estado_k4": result["estado"],
    }


@router.get("/ficha", dependencies=[Depends(require_fr04_detail)])
def patient_week(
    escenario: Scenario, semana_inicio: date,
    codigo_paciente: str = Query(min_length=1, max_length=120), poblacion: Population = "incluidos",
):
    check_week(semana_inicio)
    try:
        with datamart_connection() as conn:
            patient = fetch_one(conn, PATIENT_WEEK, (escenario, poblacion == "incluidos", semana_inicio, codigo_paciente))
        if patient is None:
            raise HTTPException(status_code=404, detail="El paciente no figura en intervención en esa semana y población")
        with connection() as conn:
            rows = fetch_all(conn, PATIENT_SESSIONS,
                             (patient["id_paciente"], semana_inicio, semana_inicio + timedelta(days=7)))
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar la ficha semanal") from exc
    seconds = sum(row["segundos"] or 0 for row in rows)
    return {
        "paciente": {"codigo_paciente": patient["codigo_paciente"], "escenario": escenario},
        "semana_inicio": semana_inicio, "semana_fin": semana_inicio + timedelta(days=6),
        "dosis": {"sesiones_realizadas": patient["sesiones"], "minutos_realizados": round(seconds / 60, 2)},
        "clasificacion": "CUMPLE" if patient["cumple"] else "NO_CUMPLE",
        "sesiones": [{**row, "minutos_realizados": round(row["segundos"] / 60, 2)
                      if row["segundos"] is not None else None} for row in rows],
    }
