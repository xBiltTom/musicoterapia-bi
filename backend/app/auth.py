"""Inicio de sesión y permisos sobre las cuentas de SQL Server."""

import hashlib
import logging
import os
import secrets
from _thread import LockType
from contextlib import closing
from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Annotated

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr

from .db import (
    DB_ERRORS, READ_ONLY, TRANSIENT_SQL_STATES, USE_AZURE, DatabaseConnectionError, connection, execute_query,
    fetch_all, fetch_one, session_write_connection, sqlstate,
)


router = APIRouter(prefix="/api/auth", tags=["Autenticación"])
COOKIE_NAME = "musicoterapia_sesion"
SESSION_SECONDS = 8 * 60 * 60
PROFILE_CACHE_SECONDS = 120
MEMORY_SESSIONS = READ_ONLY and not USE_AZURE
password_hasher = PasswordHasher()
DUMMY_HASH = password_hasher.hash(secrets.token_urlsafe(32))
logger = logging.getLogger(__name__)

ACCOUNT = """
SELECT id_usuario_sistema, password_hash, activo
FROM dbo.usuario_sistema
WHERE username = ?
"""

ACTIVE_PROFILE = """
SELECT u.id_usuario_sistema, u.codigo_personal, u.nombre_completo, u.cargo_operativo,
       r.codigo_rol, r.alcance_datos, p.codigo_permiso
FROM dbo.usuario_sistema AS u
JOIN dbo.rol_sistema AS r ON r.id_rol_sistema = u.id_rol_sistema
LEFT JOIN dbo.rol_permiso AS rp ON rp.id_rol_sistema = r.id_rol_sistema
LEFT JOIN dbo.permiso AS p ON p.id_permiso = rp.id_permiso
WHERE u.activo = 1
"""

SESSION_ACCOUNT = ACTIVE_PROFILE + """
AND EXISTS (
    SELECT 1 FROM dbo.sesion_autenticacion AS s WHERE s.id_usuario_sistema = u.id_usuario_sistema
        AND s.token_hash = ? AND s.expira_utc > SYSUTCDATETIME()
)
"""


class LoginInput(BaseModel):
    usuario: str = Field(min_length=1, max_length=60)
    contrasena: SecretStr = Field(min_length=1, max_length=256)


class Permissions(BaseModel):
    ver_tablero: bool
    ver_respuesta: bool = False
    ver_evaluaciones: bool = False
    ver_agitacion: bool = False
    ver_fr04: bool
    ver_ficha_fr04: bool = False
    editar_fr04: bool
    registrar_altas: bool
    registrar_perfil_clinico: bool
    registrar_preferencias: bool
    registrar_sesiones: bool
    registrar_musica: bool


class UserProfile(BaseModel):
    id_usuario_sistema: int = Field(exclude=True)
    codigo_personal: str
    nombre_completo: str
    rol: str
    alcance_datos: str
    solo_lectura: bool = False
    permisos: Permissions


@dataclass
class MemorySession:
    profile: UserProfile
    expires_at: float
    refresh_at: float
    refresh_lock: LockType = field(default_factory=Lock)


memory_sessions: dict[str, MemorySession] = {}
memory_lock = Lock()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
            encoded = password.encode("utf-8")
            return len(encoded) <= 72 and bcrypt.checkpw(encoded, password_hash.encode("ascii"))
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, ValueError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_token(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    return token if token and len(token) == 43 and token.isascii() else None


def session_required() -> HTTPException:
    return HTTPException(status_code=401, detail="Inicia sesión para continuar")


def load_profile(sql, lookup) -> UserProfile | None:
    for attempt in range(2):
        try:
            with connection(query_timeout=8) as conn:
                rows = fetch_all(conn, sql, (lookup,))
            break
        except DatabaseConnectionError as exc:
            raise HTTPException(status_code=503, detail="La base de datos no está disponible. Inténtalo de nuevo.") from exc
        except DB_ERRORS as exc:
            state = sqlstate(exc)
            if attempt == 0 and state in TRANSIENT_SQL_STATES:
                continue
            logger.warning("No se pudo leer el perfil de sesión (SQLSTATE %s)", state)
            raise HTTPException(status_code=503, detail="No se pudo verificar la sesión") from exc

    if not rows:
        return None

    account = rows[0]
    grants = {row["codigo_permiso"] for row in rows}
    global_access = account["alcance_datos"] == "GLOBAL"
    response = "VER_RP01" in grants
    evaluations = global_access and "VER_RP02" in grants
    weekly = global_access and bool({"VER_RP03", "REGISTRAR_FR04"} & grants)
    agitation = "VER_RP04" in grants
    return UserProfile(
        id_usuario_sistema=account["id_usuario_sistema"],
        codigo_personal=account["codigo_personal"],
        nombre_completo=account["nombre_completo"],
        rol=account["codigo_rol"],
        alcance_datos=account["alcance_datos"],
        solo_lectura=READ_ONLY,
        permisos=Permissions(
            ver_tablero=response or evaluations or weekly or agitation,
            ver_respuesta=response,
            ver_evaluaciones=evaluations,
            ver_agitacion=agitation,
            ver_fr04=weekly,
            ver_ficha_fr04=weekly,
            editar_fr04=False,
            registrar_altas=global_access and "REGISTRAR_FR01_ALTA" in grants,
            registrar_perfil_clinico=global_access and "REGISTRAR_FR01_CLIN" in grants,
            registrar_preferencias=global_access and "REGISTRAR_FR01_PREF" in grants,
            registrar_sesiones="REGISTRAR_FR03" in grants,
            registrar_musica="REGISTRAR_FR02" in grants,
        ),
    )


def active_memory_session(digest) -> MemorySession:
    with memory_lock:
        session = memory_sessions.get(digest)
        if session is None:
            raise session_required()
        if session.expires_at <= monotonic():
            del memory_sessions[digest]
            raise session_required()
        return session


def current_memory_profile(digest) -> UserProfile:
    session = active_memory_session(digest)
    if session.refresh_at > monotonic():
        return session.profile

    with session.refresh_lock:
        if active_memory_session(digest) is not session:
            raise session_required()
        if session.refresh_at > monotonic():
            return session.profile
        profile = load_profile(ACTIVE_PROFILE + " AND u.id_usuario_sistema = ?", session.profile.id_usuario_sistema)
        if profile is None:
            with memory_lock:
                memory_sessions.pop(digest, None)
            raise session_required()
        if active_memory_session(digest) is not session:
            raise session_required()
        session.profile = profile
        session.refresh_at = monotonic() + PROFILE_CACHE_SECONDS
        return profile


def current_user(request: Request) -> UserProfile:
    token = session_token(request)
    if not token:
        raise session_required()
    digest = token_hash(token)
    if MEMORY_SESSIONS:
        return current_memory_profile(digest)
    profile = load_profile(SESSION_ACCOUNT, digest)
    if profile is None:
        raise session_required()
    return profile


AuthenticatedUser = Annotated[UserProfile, Depends(current_user)]


def require_dashboard(user: Annotated[UserProfile, Depends(current_user)]):
    if not user.permisos.ver_tablero:
        raise HTTPException(status_code=403, detail="Tu rol no tiene acceso a este tablero")
    return user


def require_fr04(user: Annotated[UserProfile, Depends(current_user)]):
    if not user.permisos.ver_fr04:
        raise HTTPException(status_code=403, detail="Tu rol no tiene acceso al control semanal")
    return user


def require_fr04_detail(user: Annotated[UserProfile, Depends(require_fr04)]):
    if not user.permisos.ver_ficha_fr04:
        raise HTTPException(status_code=403, detail="Tu rol no tiene acceso a fichas individuales de FR04")


def require_json(request: Request):
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(status_code=415, detail="La solicitud debe enviarse como JSON")


def bad_credentials() -> HTTPException:
    return HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")


def register_session(account_id, password_hash, token, previous):
    digest = token_hash(token)
    previous_digest = token_hash(previous) if previous else None
    if MEMORY_SESSIONS:
        profile = load_profile(ACTIVE_PROFILE + " AND u.id_usuario_sistema = ?", account_id)
        if profile is None:
            raise bad_credentials()
        with memory_lock:
            now = monotonic()
            for expired in [key for key, value in memory_sessions.items() if value.expires_at <= now]:
                del memory_sessions[expired]
            if previous_digest:
                memory_sessions.pop(previous_digest, None)
            memory_sessions[digest] = MemorySession(profile, now + SESSION_SECONDS, now + PROFILE_CACHE_SECONDS)
        return

    with session_write_connection() as conn:
        with closing(conn.cursor()) as cursor:
            account_check = (
                """SELECT id_usuario_sistema FROM dbo.usuario_sistema
                   WHERE id_usuario_sistema = ? AND activo = 1 AND password_hash = ?"""
                if READ_ONLY else
                """UPDATE dbo.usuario_sistema SET ultimo_acceso = SYSUTCDATETIME()
                   OUTPUT INSERTED.id_usuario_sistema
                   WHERE id_usuario_sistema = ? AND activo = 1 AND password_hash = ?"""
            )
            execute_query(cursor, account_check, (account_id, password_hash))
            if cursor.fetchone() is None:
                raise bad_credentials()
            execute_query(cursor, "DELETE FROM dbo.sesion_autenticacion WHERE expira_utc <= SYSUTCDATETIME()")
            if previous_digest:
                execute_query(cursor, "DELETE FROM dbo.sesion_autenticacion WHERE token_hash = ?", (previous_digest,))
            execute_query(
                cursor,
                """INSERT INTO dbo.sesion_autenticacion (token_hash, id_usuario_sistema, expira_utc)
                   VALUES (?, ?, DATEADD(second, ?, SYSUTCDATETIME()))""",
                (digest, account_id, SESSION_SECONDS),
            )


@router.post("/login", status_code=204, dependencies=[Depends(require_json)])
def login(payload: LoginInput, request: Request, response: Response):
    username = payload.usuario.strip()
    try:
        with connection() as conn:
            account = fetch_one(conn, ACCOUNT, (username,)) if username else None

        active = account is not None and account["activo"]
        password_hash = account["password_hash"] if active else DUMMY_HASH
        if not verify_password(payload.contrasena.get_secret_value(), password_hash) or not active:
            raise bad_credentials()

        token = secrets.token_urlsafe(32)
        register_session(account["id_usuario_sistema"], password_hash, token, session_token(request))
    except DatabaseConnectionError as exc:
        raise HTTPException(status_code=503, detail="La base de datos no está disponible. Inténtalo de nuevo.") from exc
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo iniciar sesión") from exc

    response.set_cookie(
        key=COOKIE_NAME, value=token, max_age=SESSION_SECONDS, httponly=True, samesite="strict",
        secure=USE_AZURE or os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true",
    )


@router.get("/sesion", response_model=UserProfile)
def profile(user: Annotated[UserProfile, Depends(current_user)]) -> UserProfile:
    return user


@router.post("/logout", status_code=204, dependencies=[Depends(require_json)])
def logout(request: Request, response: Response):
    token = session_token(request)
    if token and MEMORY_SESSIONS:
        with memory_lock:
            memory_sessions.pop(token_hash(token), None)
    elif token:
        try:
            with session_write_connection() as conn:
                with closing(conn.cursor()) as cursor:
                    execute_query(cursor, "DELETE FROM dbo.sesion_autenticacion WHERE token_hash = ?", (token_hash(token),))
        except DB_ERRORS as exc:
            raise HTTPException(status_code=503, detail="No se pudo cerrar la sesión") from exc
    response.delete_cookie(
        COOKIE_NAME, httponly=True, samesite="strict",
        secure=USE_AZURE or os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true",
    )
