"""Captura transaccional de música utilizada (FR02) y diario de sesión (FR03)."""

from contextlib import closing
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import AfterValidator, Field, NaiveDatetime, field_validator, model_validator

from .auth import AuthenticatedUser
from .db import DB_ERRORS, READ_ONLY, connection, fetch_all, fetch_one, has_column, write_connection
from .pacientes import FormInput, Scenario, Text, lock_patient


router = APIRouter(prefix="/api/sesiones", tags=["FR02 y FR03 · Sesiones"])
PositiveId = Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)]
AgitationScore = Annotated[int, Field(ge=0, le=16)]


def validate_precision(value: datetime):
    if value.microsecond:
        raise ValueError("Registra las horas con precisión de segundos")
    return value


SessionTime = Annotated[NaiveDatetime, AfterValidator(validate_precision)]

PLAYLIST_SCENARIO = """
    EXISTS (SELECT 1 FROM dbo.lista_reproduccion_cancion AS lc
            WHERE lc.id_lista_reproduccion = l.id_lista_reproduccion)
    AND NOT EXISTS (
        SELECT 1 FROM dbo.lista_reproduccion_cancion AS lc
        JOIN dbo.cancion AS c ON c.id_cancion = lc.id_cancion
        WHERE lc.id_lista_reproduccion = l.id_lista_reproduccion AND c.escenario <> ?
    )
"""

SESSION_SELECT = """
    SELECT s.id_sesion_musical, s.codigo_sesion, s.fecha_hora_inicio_sesion, s.fecha_hora_fin_sesion,
           s.modalidad_sesion, s.tipo_actividad, {music_use}, u.codigo_personal
    FROM dbo.sesion_musical AS s
    JOIN dbo.usuario_sistema AS u ON u.id_usuario_sistema = s.id_responsable
    WHERE (? = 1 OR s.id_responsable = ?) AND EXISTS (
        SELECT 1 FROM dbo.participacion_sesion AS ps
        JOIN dbo.paciente AS p ON p.id_paciente = ps.id_paciente
        WHERE ps.id_sesion_musical = s.id_sesion_musical AND p.escenario = ?
    )
"""


def session_select(conn):
    available = not READ_ONLY or has_column(conn, "dbo.sesion_musical", "uso_musica")
    music_use = """CASE WHEN s.id_lista_reproduccion IS NOT NULL THEN N'LISTA'
                        WHEN s.fecha_hora_inicio_musica IS NOT NULL THEN N'SIN_DETALLE' END"""
    if available:
        music_use = f"COALESCE(s.uso_musica, {music_use})"
    return SESSION_SELECT.format(music_use=f"{music_use} AS uso_musica")


class TrackInput(FormInput):
    id_cancion: PositiveId
    inicio: SessionTime
    fin: SessionTime


class ParticipationInput(FormInput):
    id_paciente: PositiveId
    estado: Literal["COMPLETA", "INTERRUMPIDA", "AUSENTE"]
    ingreso: SessionTime | None = None
    salida: SessionTime | None = None
    motivo_interrupcion: Text | None = None
    experiencia: Literal["POSITIVA", "NEUTRA", "NEGATIVA", "NO_SABE"] | None = None
    efecto_resto_dia: Literal["POSITIVO", "NEUTRO", "NEGATIVO", "NO_SABE"] | None = None
    estado_respuesta: Literal["OBSERVADA", "SIN_RESPUESTA", "NO_OBSERVADA"] | None = None
    primera_respuesta: SessionTime | None = None
    agitacion_antes: AgitationScore | None = None
    agitacion_despues: AgitationScore | None = None
    comentarios: Text | None = None
    pistas: list[TrackInput] = Field(default_factory=list, max_length=30)


class SessionInput(FormInput):
    codigo_sesion: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
    escenario: Scenario
    modalidad: Literal["INDIVIDUAL", "GRUPAL"]
    actividad: Literal["ESCUCHA", "CANTO", "ESTIMULACION_SENSORIAL", "OTRA"]
    inicio: SessionTime
    fin: SessionTime
    uso_musica: Literal["SIN_MUSICA", "SIN_DETALLE", "PISTAS", "LISTA"]
    inicio_musica: SessionTime | None = None
    id_lista_reproduccion: PositiveId | None = None
    participantes: list[ParticipationInput] = Field(min_length=1, max_length=25)

    @field_validator("codigo_sesion")
    @classmethod
    def normalize_code(cls, value):
        return value.upper()

    @model_validator(mode="after")
    def validate_session(self):
        if not timedelta(0) < self.fin - self.inicio <= timedelta(days=1):
            raise ValueError("La sesión debe tener una duración positiva de hasta 24 horas")
        if self.inicio_musica and not self.inicio <= self.inicio_musica < self.fin:
            raise ValueError("El inicio de la música debe estar dentro de la sesión")
        if self.uso_musica == "SIN_MUSICA" and self.inicio_musica:
            raise ValueError("Una sesión sin música no puede tener hora de inicio de música")
        if (self.uso_musica == "LISTA") != (self.id_lista_reproduccion is not None):
            raise ValueError("Selecciona una lista únicamente si se utilizó una lista de reproducción")
        if self.modalidad == "INDIVIDUAL" and len(self.participantes) != 1:
            raise ValueError("Una sesión individual admite un solo participante")
        if len({p.id_paciente for p in self.participantes}) != len(self.participantes):
            raise ValueError("Cada paciente debe aparecer una sola vez en la sesión")
        if self.uso_musica == "PISTAS" and not any(p.pistas for p in self.participantes):
            raise ValueError("Añade al menos una pista para identificar la música utilizada")
        if sum(len(p.pistas) for p in self.participantes) > 100:
            raise ValueError("Una sesión admite hasta 100 registros de pistas")
        for p in self.participantes:
            self.validate_participation(p)
        return self

    def validate_participation(self, p):
        if p.estado == "AUSENTE":
            observations = (p.ingreso, p.salida, p.motivo_interrupcion, p.experiencia, p.efecto_resto_dia,
                            p.estado_respuesta, p.primera_respuesta, p.agitacion_antes, p.agitacion_despues)
            if p.pistas or any(value is not None for value in observations):
                raise ValueError("Un paciente ausente solo admite comentarios")
            return

        if (p.ingreso is None) != (p.salida is None) or (p.estado == "INTERRUMPIDA" and p.ingreso is None):
            raise ValueError("Registra ingreso y salida juntos. Son obligatorios si la participación se interrumpió")
        if p.motivo_interrupcion and p.estado != "INTERRUMPIDA":
            raise ValueError("El motivo solo corresponde a una participación interrumpida")
        start = p.ingreso or self.inicio
        end = p.salida or self.fin
        if not self.inicio <= start < end <= self.fin:
            raise ValueError("El ingreso y la salida del paciente deben estar dentro de la sesión")
        if (p.estado_respuesta == "OBSERVADA") != (p.primera_respuesta is not None):
            raise ValueError("La hora de primera respuesta se registra solo si hubo respuesta observada")
        if self.uso_musica == "SIN_MUSICA" and p.estado_respuesta in ("OBSERVADA", "SIN_RESPUESTA"):
            raise ValueError("La observación de respuesta musical requiere una sesión con música")
        if p.primera_respuesta and (
            self.inicio_musica is None or not max(start, self.inicio_musica) <= p.primera_respuesta <= end
        ):
            raise ValueError("La primera respuesta debe ocurrir después de iniciar la música y durante la participación")
        if p.pistas and self.uso_musica not in ("PISTAS", "LISTA"):
            raise ValueError("Las pistas se registran cuando se identificó la música utilizada")
        previous_end = max(start, self.inicio_musica) if self.inicio_musica else start
        for track in sorted(p.pistas, key=lambda item: item.inicio):
            if not previous_end <= track.inicio < track.fin <= end:
                raise ValueError("Las pistas deben estar dentro de la participación y no pueden superponerse")
            previous_end = track.fin


def require_sessions(user):
    if not user.permisos.registrar_sesiones:
        raise HTTPException(status_code=403, detail="Tu rol no puede acceder al diario de sesiones")


@router.get("/pacientes")
def patient_options(
    user: AuthenticatedUser, escenario: Scenario, fecha: date,
    buscar: str = Query(default="", max_length=60),
):
    require_sessions(user)
    search = buscar.strip()
    global_access = user.alcance_datos == "GLOBAL"
    if not global_access and not search:
        return []
    try:
        with connection() as conn:
            return fetch_all(conn, """
                SELECT TOP (15) id_paciente, codigo_paciente FROM dbo.paciente
                WHERE escenario = ? AND fecha_ingreso_programa <= ?
                  AND (fecha_salida_programa IS NULL OR fecha_salida_programa >= ?)
                  AND ((? = 1 AND (? = N'' OR CHARINDEX(?, codigo_paciente) = 1)) OR codigo_paciente = ?)
                ORDER BY codigo_paciente
            """, (escenario, fecha, fecha, global_access, search, search, search))
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo buscar participantes") from exc


@router.get("/musica")
def music_options(user: AuthenticatedUser, escenario: Scenario, buscar: str = Query(default="", max_length=100)):
    require_sessions(user)
    if not user.permisos.registrar_musica:
        raise HTTPException(status_code=403, detail="Tu rol no puede registrar música del catálogo")
    search = buscar.strip()
    try:
        with connection() as conn:
            tracks = fetch_all(conn, """
                SELECT TOP (30) id_cancion, titulo_cancion, nombre_album, anio_publicacion
                FROM dbo.cancion WHERE escenario = ? AND (? = N'' OR CHARINDEX(?, titulo_cancion) > 0)
                ORDER BY titulo_cancion, id_cancion
            """, (escenario, search, search))
            playlists = fetch_all(conn, f"""
                SELECT TOP (30) l.id_lista_reproduccion, l.nombre_lista_reproduccion
                FROM dbo.lista_reproduccion AS l WHERE {PLAYLIST_SCENARIO}
                    AND (? = N'' OR CHARINDEX(?, l.nombre_lista_reproduccion) > 0)
                ORDER BY l.nombre_lista_reproduccion, l.id_lista_reproduccion
            """, (escenario, search, search))
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar el catálogo musical") from exc
    return {"pistas": tracks, "listas": playlists}


@router.get("")
def list_sessions(
    user: AuthenticatedUser, escenario: Scenario,
    buscar: str = Query(default="", max_length=100), pagina: int = Query(default=1, ge=1, le=10_000),
):
    require_sessions(user)
    search = buscar.strip()
    try:
        with connection() as conn:
            rows = fetch_all(conn, session_select(conn) + """
                AND (? = N'' OR CHARINDEX(?, s.codigo_sesion) = 1)
                ORDER BY s.fecha_hora_inicio_sesion DESC, s.id_sesion_musical DESC
                OFFSET ? ROWS FETCH NEXT 26 ROWS ONLY
            """, (user.alcance_datos == "GLOBAL", user.id_usuario_sistema, escenario, search, search, (pagina - 1) * 25))
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar el diario de sesiones") from exc
    return {"sesiones": rows[:25], "hay_mas": len(rows) > 25}


@router.get("/{session_id}")
def get_session(session_id: PositiveId, escenario: Scenario, user: AuthenticatedUser):
    require_sessions(user)
    try:
        with connection() as conn:
            session = fetch_one(conn, session_select(conn) + " AND s.id_sesion_musical = ?",
                                (user.alcance_datos == "GLOBAL", user.id_usuario_sistema, escenario, session_id))
            if not session:
                raise HTTPException(status_code=404, detail="Sesión no encontrada")
            header = fetch_one(conn, """
                SELECT s.fecha_hora_inicio_musica, l.nombre_lista_reproduccion
                FROM dbo.sesion_musical AS s LEFT JOIN dbo.lista_reproduccion AS l
                    ON l.id_lista_reproduccion = s.id_lista_reproduccion WHERE s.id_sesion_musical = ?
            """, (session_id,))
            participants = fetch_all(conn, """
                SELECT ps.id_participacion_sesion, p.codigo_paciente, ps.estado_participacion,
                       ps.fecha_hora_ingreso_paciente, ps.fecha_hora_salida_paciente, ps.motivo_interrupcion,
                       ps.experiencia_sesion, ps.efecto_resto_dia, ps.estado_respuesta_positiva,
                       ps.fecha_hora_primera_respuesta, ps.minutos_hasta_primera_respuesta,
                       ps.puntaje_agitacion_antes, ps.puntaje_agitacion_despues, ps.comentarios
                FROM dbo.participacion_sesion AS ps JOIN dbo.paciente AS p ON p.id_paciente = ps.id_paciente
                WHERE ps.id_sesion_musical = ? AND p.escenario = ? ORDER BY p.codigo_paciente
            """, (session_id, escenario))
            tracks = fetch_all(conn, """
                SELECT x.id_participacion_sesion, x.orden_reproduccion, c.titulo_cancion,
                       x.fecha_hora_inicio_cancion, x.fecha_hora_fin_cancion
                FROM dbo.exposicion_musical AS x JOIN dbo.cancion AS c ON c.id_cancion = x.id_cancion
                JOIN dbo.participacion_sesion AS ps ON ps.id_participacion_sesion = x.id_participacion_sesion
                JOIN dbo.paciente AS p ON p.id_paciente = ps.id_paciente
                WHERE ps.id_sesion_musical = ? AND p.escenario = ? ORDER BY x.orden_reproduccion
            """, (session_id, escenario))
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar la sesión") from exc
    for participant in participants:
        participant_id = participant["id_participacion_sesion"]
        participant["pistas"] = [track for track in tracks if track["id_participacion_sesion"] == participant_id]
    if tracks and session["uso_musica"] in (None, "SIN_DETALLE"):
        session["uso_musica"] = "PISTAS"
    return {"sesion": {**session, **header}, "participantes": participants}


def insert_participation(conn, session_id, session, p):
    start = (p.ingreso or session.inicio) if p.estado != "AUSENTE" else None
    end = (p.salida or session.fin) if p.estado != "AUSENTE" else None
    latency = None
    if p.primera_respuesta is not None:
        seconds = int((p.primera_respuesta - session.inicio_musica).total_seconds())
        latency = (Decimal(seconds) / 60).quantize(Decimal("0.01"))
    row = fetch_one(conn, """
        INSERT INTO dbo.participacion_sesion (id_sesion_musical, id_paciente, fecha_hora_ingreso_paciente,
            fecha_hora_salida_paciente, estado_participacion, motivo_interrupcion, experiencia_sesion,
            efecto_resto_dia, estado_respuesta_positiva, fecha_hora_primera_respuesta,
            minutos_hasta_primera_respuesta, puntaje_agitacion_antes, puntaje_agitacion_despues, comentarios)
        OUTPUT INSERTED.id_participacion_sesion VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, p.id_paciente, start, end, p.estado, p.motivo_interrupcion, p.experiencia, p.efecto_resto_dia,
          p.estado_respuesta, p.primera_respuesta, latency, p.agitacion_antes, p.agitacion_despues, p.comentarios))
    if p.pistas:
        with closing(conn.cursor()) as cursor:
            cursor.executemany("""
                INSERT INTO dbo.exposicion_musical (id_participacion_sesion, id_cancion, orden_reproduccion,
                    fecha_hora_inicio_cancion, fecha_hora_fin_cancion) VALUES (?, ?, ?, ?, ?)
            """, [(row["id_participacion_sesion"], track.id_cancion, index, track.inicio, track.fin)
                   for index, track in enumerate(sorted(p.pistas, key=lambda item: item.inicio), start=1)])


@router.post("", status_code=201)
def create_session(payload: SessionInput, user: AuthenticatedUser):
    require_sessions(user)
    if payload.uso_musica in ("PISTAS", "LISTA") and not user.permisos.registrar_musica:
        raise HTTPException(status_code=403, detail="Tu rol no puede asociar pistas o listas a la sesión")
    try:
        with write_connection() as conn:
            existing = fetch_one(conn, """
                SELECT id_sesion_musical FROM dbo.sesion_musical WITH (UPDLOCK, HOLDLOCK) WHERE codigo_sesion = ?
            """, (payload.codigo_sesion,))
            if existing is not None:
                raise HTTPException(status_code=409, detail="Ya existe una sesión con ese código")
            for participant_id in sorted(p.id_paciente for p in payload.participantes):
                patient = lock_patient(conn, participant_id)
                start_date = payload.inicio.date()
                if patient["escenario"] != payload.escenario or patient["fecha_ingreso_programa"] > start_date or (
                    patient["fecha_salida_programa"] is not None and patient["fecha_salida_programa"] < start_date
                ):
                    raise HTTPException(status_code=422, detail="Todos los participantes deben estar inscritos en ese escenario y fecha")
            if payload.id_lista_reproduccion is not None and not fetch_one(conn, f"""
                SELECT l.id_lista_reproduccion FROM dbo.lista_reproduccion AS l
                WHERE l.id_lista_reproduccion = ? AND {PLAYLIST_SCENARIO}
            """, (payload.id_lista_reproduccion, payload.escenario)):
                raise HTTPException(status_code=422, detail="La lista no está disponible en este escenario")
            track_ids = {track.id_cancion for p in payload.participantes for track in p.pistas}
            for track_id in sorted(track_ids):
                if not fetch_one(conn, "SELECT id_cancion FROM dbo.cancion WHERE id_cancion = ? AND escenario = ?",
                                 (track_id, payload.escenario)):
                    raise HTTPException(status_code=422, detail="Una pista no está disponible en este escenario")
            session = fetch_one(conn, """
                INSERT INTO dbo.sesion_musical (codigo_sesion, modalidad_sesion, tipo_actividad,
                    fecha_hora_inicio_sesion, fecha_hora_fin_sesion, fecha_hora_inicio_musica, uso_musica,
                    id_lista_reproduccion, id_responsable)
                OUTPUT INSERTED.id_sesion_musical, INSERTED.codigo_sesion VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (payload.codigo_sesion, payload.modalidad, payload.actividad, payload.inicio, payload.fin,
                  payload.inicio_musica, payload.uso_musica, payload.id_lista_reproduccion, user.id_usuario_sistema))
            for participant in payload.participantes:
                insert_participation(conn, session["id_sesion_musical"], payload, participant)
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo registrar la sesión") from exc
    return session
