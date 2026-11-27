"""Ficha FR01 con alta, historia clínica de ingreso y preferencias musicales."""

import logging
from contextlib import closing
from datetime import date
from decimal import Decimal
from time import monotonic
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .auth import AuthenticatedUser
from .db import (
    DB_ERRORS, READ_ONLY, TRANSIENT_SQL_STATES, DatabaseConnectionError, connection, fetch_all, fetch_one, has_table,
    sqlstate, table_columns, write_connection,
)
from .patient_directory import PATIENT_FIELDS, patient_directory


router = APIRouter(prefix="/api/pacientes", tags=["FR01 · Pacientes"])
Scenario = Literal["HIBRIDO", "SINTETICO_IA"]
Code = Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")]
Text = Annotated[str, Field(min_length=1, max_length=500)]

PATIENT_PAGE_SIZE = 25
logger = logging.getLogger(__name__)


def code_prefix_pattern(value: str) -> str:
    return value.translate(str.maketrans({"~": "~~", "%": "~%", "_": "~_", "[": "~["})) + "%"


class FormInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProgramInput(FormInput):
    sexo: Literal["MASCULINO", "FEMENINO", "NO_ESPECIFICADO"] | None = None
    fecha_ingreso_programa: date
    fecha_salida_programa: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.fecha_salida_programa and self.fecha_salida_programa < self.fecha_ingreso_programa:
            raise ValueError("La salida del programa debe ser igual o posterior al ingreso")
        return self


class PatientInput(ProgramInput):
    codigo_paciente: Code
    escenario: Scenario

    @field_validator("codigo_paciente")
    @classmethod
    def normalize_code(cls, value):
        return value.upper()


class ClinicalInput(FormInput):
    fecha_visita: date
    edad_paciente_en_visita: Annotated[Decimal, Field(ge=0, le=130, decimal_places=2)] | None = None
    anios_educacion_completados: Annotated[int, Field(ge=0, le=80)] | None = None
    nombre_diagnostico: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    codigo_cie10: Annotated[str, Field(min_length=1, max_length=16)] | None = None
    tiene_diagnostico_alzheimer: bool | None = None
    etapa_alzheimer: Literal["LEVE", "MODERADA", "OTRA", "NO_CONSTA"] | None = None
    antecedentes_fr01: Text | None = None
    tabaquismo_fr01: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    gold_msi_fr01: Annotated[Decimal, Field(ge=0, max_digits=7, decimal_places=2)] | None = None
    antipsicoticos_fr01: bool | None = None
    antidepresivos_fr01: bool | None = None
    ansioliticos_fr01: bool | None = None

    @model_validator(mode="after")
    def validate_clinical(self):
        if not any(value is not None for value in self.model_dump(exclude={"fecha_visita"}).values()):
            raise ValueError("Completa al menos un dato del perfil clínico")
        if self.tiene_diagnostico_alzheimer is False and self.etapa_alzheimer in ("LEVE", "MODERADA"):
            raise ValueError("Una etapa de Alzheimer requiere un diagnóstico compatible")
        return self


class PreferencesInput(FormInput):
    fuente: Literal["PACIENTE", "FAMILIAR", "CUIDADOR", "OTRA"]
    antecedentes: Text | None = None
    preferencias: Text | None = None
    musica_a_evitar: Text | None = None
    observaciones: Text | None = None

    @model_validator(mode="after")
    def validate_preferences(self):
        if not any((self.antecedentes, self.preferencias, self.musica_a_evitar, self.observaciones)):
            raise ValueError("Completa al menos un dato de preferencias musicales")
        return self


def require_patient_access(user):
    p = user.permisos
    if not (p.registrar_altas or p.registrar_perfil_clinico or p.registrar_preferencias):
        raise HTTPException(status_code=403, detail="Tu rol no tiene acceso a la ficha del paciente")


def read_patient(conn, patient_id):
    patient = fetch_one(conn, f"SELECT {PATIENT_FIELDS} FROM dbo.paciente WHERE id_paciente = ?", (patient_id,))
    if patient is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return patient


def lock_patient(conn, patient_id):
    patient = fetch_one(
        conn, f"SELECT {PATIENT_FIELDS} FROM dbo.paciente WITH (UPDLOCK, HOLDLOCK) WHERE id_paciente = ?", (patient_id,),
    )
    if patient is None:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    return patient


@router.get("")
def list_patients(
    user: AuthenticatedUser,
    background_tasks: BackgroundTasks,
    escenario: Scenario = "HIBRIDO",
    buscar: str = Query(default="", max_length=60),
    pagina: int = Query(default=1, ge=1, le=10_000),
):
    require_patient_access(user)
    prefix = buscar.strip()
    offset = (pagina - 1) * PATIENT_PAGE_SIZE
    if READ_ONLY:
        snapshot = patient_directory.get()
        if snapshot is None:
            raise HTTPException(status_code=503, detail="El directorio aún no pudo cargar los pacientes desde SQL Server")
        if patient_directory.needs_refresh():
            background_tasks.add_task(patient_directory.refresh)
        matches = snapshot.matching(escenario, prefix)
        return page_result(matches[offset:offset + PATIENT_PAGE_SIZE], pagina, len(matches),
                           snapshot.loaded_at, monotonic() >= snapshot.refresh_at)

    query_filter = "escenario = ?"
    parameters = (escenario,)
    if prefix:
        query_filter += " AND codigo_paciente LIKE ? ESCAPE N'~'"
        parameters += (code_prefix_pattern(prefix),)
    for attempt in range(2):
        try:
            with connection(query_timeout=8) as conn:
                total = fetch_one(conn, f"SELECT COUNT_BIG(*) AS total FROM dbo.paciente WHERE {query_filter}", parameters)["total"]
                rows = []
                if offset < total:
                    rows = fetch_all(
                        conn, f"""SELECT {PATIENT_FIELDS} FROM dbo.paciente WHERE {query_filter}
                                  ORDER BY codigo_paciente OFFSET ? ROWS FETCH NEXT ? ROWS ONLY""",
                        (*parameters, offset, PATIENT_PAGE_SIZE),
                    )
            break
        except DatabaseConnectionError as exc:
            raise HTTPException(status_code=503, detail="La base de datos no está disponible. Inténtalo de nuevo.") from exc
        except DB_ERRORS as exc:
            state = sqlstate(exc)
            if attempt == 0 and state in TRANSIENT_SQL_STATES:
                continue
            logger.warning("No se pudo consultar la página de pacientes (SQLSTATE %s)", state)
            raise HTTPException(status_code=503, detail="No se pudo consultar pacientes") from exc
    return page_result(rows, pagina, total)


def page_result(rows, page, total, loaded_at=None, stale=False):
    return {"pacientes": rows, "pagina": page, "tamano_pagina": PATIENT_PAGE_SIZE,
            "total": total, "total_paginas": (total + PATIENT_PAGE_SIZE - 1) // PATIENT_PAGE_SIZE,
            "hay_mas": page * PATIENT_PAGE_SIZE < total, "consultado_utc": loaded_at, "datos_desactualizados": stale}


@router.get("/{patient_id}")
def get_patient(patient_id: int, user: AuthenticatedUser):
    require_patient_access(user)
    try:
        with connection() as conn:
            patient = read_patient(conn, patient_id)
            clinical = None
            preferences = None
            medications = []
            if user.permisos.registrar_perfil_clinico:
                visit_fields = (
                    "antecedentes_fr01", "tabaquismo_fr01", "gold_msi_fr01", "antipsicoticos_fr01",
                    "antidepresivos_fr01", "ansioliticos_fr01",
                )
                diagnosis_fields = ("codigo_cie10", "etapa_alzheimer")
                visit_columns = table_columns(conn, "dbo.visita_clinica") if READ_ONLY else set(visit_fields)
                diagnosis_columns = table_columns(conn, "dbo.diagnostico_paciente") if READ_ONLY else set(diagnosis_fields)
                visit_extras = ", ".join(
                    f"v.{field}" if field in visit_columns else f"NULL AS {field}"
                    for field in visit_fields
                )
                diagnosis_extras = ", ".join(
                    field if field in diagnosis_columns else f"NULL AS {field}"
                    for field in diagnosis_fields
                )
                clinical = fetch_one(conn, f"""
                    SELECT TOP (1) v.id_visita_clinica, v.fecha_visita, v.edad_paciente_en_visita, v.anios_educacion_completados,
                           {visit_extras}, d.nombre_diagnostico, d.codigo_cie10,
                           d.tiene_diagnostico_alzheimer, d.etapa_alzheimer
                    FROM dbo.visita_clinica AS v
                    OUTER APPLY (
                        SELECT TOP (1) nombre_diagnostico, tiene_diagnostico_alzheimer, {diagnosis_extras}
                        FROM dbo.diagnostico_paciente
                        WHERE id_visita_clinica = v.id_visita_clinica AND id_paciente = v.id_paciente
                        ORDER BY fecha_diagnostico DESC, id_diagnostico_paciente DESC
                    ) AS d
                    WHERE v.id_paciente = ?
                    ORDER BY v.fecha_visita DESC, v.numero_visita DESC
                """, (patient_id,))
                if READ_ONLY and clinical:
                    medications = [row["nombre_medicamento"] for row in fetch_all(conn, """
                        SELECT DISTINCT m.nombre_medicamento FROM dbo.medicamento_paciente_visita AS mv
                        JOIN dbo.medicamento AS m ON m.id_medicamento = mv.id_medicamento
                        WHERE mv.id_visita_clinica = ? ORDER BY m.nombre_medicamento
                    """, (clinical["id_visita_clinica"],))]
            if user.permisos.registrar_preferencias and (not READ_ONLY or has_table(conn, "dbo.preferencia_musical_paciente")):
                preferences = fetch_one(conn, """
                    SELECT fuente, antecedentes, preferencias, musica_a_evitar, observaciones, fecha_actualizacion_utc
                    FROM dbo.preferencia_musical_paciente WHERE id_paciente = ?
                """, (patient_id,))
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar la ficha del paciente") from exc
    return {"paciente": patient, "perfil_clinico": clinical, "medicamentos": medications, "preferencias": preferences}


@router.post("", status_code=201)
def create_patient(payload: PatientInput, user: AuthenticatedUser):
    if not user.permisos.registrar_altas:
        raise HTTPException(status_code=403, detail="Tu rol no puede dar de alta pacientes")
    try:
        with write_connection() as conn:
            existing = fetch_one(conn, """
                SELECT id_paciente FROM dbo.paciente WITH (UPDLOCK, HOLDLOCK) WHERE codigo_paciente = ?
            """, (payload.codigo_paciente,))
            if existing:
                raise HTTPException(status_code=409, detail="Ya existe un paciente con ese código")
            patient = fetch_one(conn, """
                INSERT INTO dbo.paciente (codigo_paciente, escenario, sexo, fecha_ingreso_programa,
                    fecha_salida_programa, id_usuario_registro)
                OUTPUT INSERTED.id_paciente, INSERTED.codigo_paciente, INSERTED.escenario, INSERTED.sexo,
                    INSERTED.fecha_ingreso_programa, INSERTED.fecha_salida_programa
                VALUES (?, ?, ?, ?, ?, ?)
            """, (payload.codigo_paciente, payload.escenario, payload.sexo, payload.fecha_ingreso_programa,
                  payload.fecha_salida_programa, user.id_usuario_sistema))
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo registrar el paciente") from exc
    return patient


@router.put("/{patient_id}/programa")
def update_program(patient_id: int, payload: ProgramInput, user: AuthenticatedUser):
    if not user.permisos.registrar_altas:
        raise HTTPException(status_code=403, detail="Tu rol no puede editar el alta del paciente")
    try:
        with write_connection() as conn:
            patient = lock_patient(conn, patient_id)
            start, end = payload.fecha_ingreso_programa, payload.fecha_salida_programa
            if (start, end) != (patient["fecha_ingreso_programa"], patient["fecha_salida_programa"]):
                conflict = fetch_one(conn, """
                    SELECT TOP (1) 1 AS conflicto
                    FROM dbo.participacion_sesion AS ps
                    JOIN dbo.sesion_musical AS s ON s.id_sesion_musical = ps.id_sesion_musical
                    WHERE ps.id_paciente = ? AND (CAST(s.fecha_hora_inicio_sesion AS date) < ?
                        OR CAST(s.fecha_hora_inicio_sesion AS date) > COALESCE(CAST(? AS date), '99991231'))
                    UNION ALL
                    SELECT TOP (1) 1 FROM dbo.control_semanal_intervencion
                    WHERE id_paciente = ? AND (DATEDIFF(day, fecha_inicio_semana, CAST(? AS date)) > 6
                        OR fecha_inicio_semana > COALESCE(CAST(? AS date), '99991231'))
                """, (patient_id, start, end, patient_id, start, end))
                if conflict:
                    raise HTTPException(status_code=409, detail="Las fechas dejarían fuera sesiones o fichas semanales existentes")
            updated = fetch_one(conn, """
                UPDATE dbo.paciente SET sexo = ?, fecha_ingreso_programa = ?, fecha_salida_programa = ?
                OUTPUT INSERTED.id_paciente, INSERTED.codigo_paciente, INSERTED.escenario, INSERTED.sexo,
                    INSERTED.fecha_ingreso_programa, INSERTED.fecha_salida_programa
                WHERE id_paciente = ?
            """, (payload.sexo, start, end, patient_id))
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo actualizar el registro del programa") from exc
    return updated


@router.post("/{patient_id}/perfil-clinico", status_code=201)
def save_clinical_profile(patient_id: int, payload: ClinicalInput, user: AuthenticatedUser):
    if not user.permisos.registrar_perfil_clinico:
        raise HTTPException(status_code=403, detail="Tu rol no puede registrar el perfil clínico")
    try:
        with write_connection() as conn:
            lock_patient(conn, patient_id)
            visit = fetch_one(conn, """
                INSERT INTO dbo.visita_clinica (id_paciente, id_centro_atencion, numero_visita, fecha_visita,
                    edad_paciente_en_visita, anios_educacion_completados, antecedentes_fr01, tabaquismo_fr01,
                    gold_msi_fr01, antipsicoticos_fr01, antidepresivos_fr01, ansioliticos_fr01, id_usuario_registro)
                OUTPUT INSERTED.id_visita_clinica
                SELECT ?, (SELECT MIN(id_centro_atencion) FROM dbo.centro_atencion HAVING COUNT(*) = 1),
                    COALESCE(MAX(numero_visita), 0) + 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                FROM dbo.visita_clinica WHERE id_paciente = ?
            """, (patient_id, payload.fecha_visita, payload.edad_paciente_en_visita, payload.anios_educacion_completados,
                  payload.antecedentes_fr01, payload.tabaquismo_fr01, payload.gold_msi_fr01,
                  payload.antipsicoticos_fr01, payload.antidepresivos_fr01, payload.ansioliticos_fr01,
                  user.id_usuario_sistema, patient_id))
            diagnostic = (payload.nombre_diagnostico, payload.codigo_cie10, payload.tiene_diagnostico_alzheimer,
                          payload.etapa_alzheimer)
            if any(value is not None for value in diagnostic):
                with closing(conn.cursor()) as cursor:
                    cursor.execute("""
                        INSERT INTO dbo.diagnostico_paciente (id_paciente, id_visita_clinica, fecha_diagnostico,
                            nombre_diagnostico, codigo_cie10, tiene_diagnostico_alzheimer, etapa_alzheimer)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, patient_id, visit["id_visita_clinica"], payload.fecha_visita, *diagnostic)
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo registrar el perfil clínico") from exc
    return {"id_visita_clinica": visit["id_visita_clinica"]}


@router.put("/{patient_id}/preferencias", status_code=204)
def save_preferences(patient_id: int, payload: PreferencesInput, user: AuthenticatedUser):
    if not user.permisos.registrar_preferencias:
        raise HTTPException(status_code=403, detail="Tu rol no puede registrar preferencias musicales")
    values = (payload.fuente, payload.antecedentes, payload.preferencias, payload.musica_a_evitar, payload.observaciones,
              user.id_usuario_sistema, patient_id)
    try:
        with write_connection() as conn:
            lock_patient(conn, patient_id)
            with closing(conn.cursor()) as cursor:
                cursor.execute("""
                    UPDATE dbo.preferencia_musical_paciente SET fuente = ?, antecedentes = ?, preferencias = ?,
                        musica_a_evitar = ?, observaciones = ?, id_usuario_registro = ?, fecha_actualizacion_utc = SYSUTCDATETIME()
                    WHERE id_paciente = ?
                """, *values)
                if cursor.rowcount == 0:
                    cursor.execute("""
                        INSERT INTO dbo.preferencia_musical_paciente (fuente, antecedentes, preferencias, musica_a_evitar,
                            observaciones, id_usuario_registro, id_paciente) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, *values)
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudieron guardar las preferencias musicales") from exc
