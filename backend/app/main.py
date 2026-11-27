"""API de musicoterapia y su tablero dimensional."""

from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import queries
from .auth import UserProfile, require_dashboard, router as auth_router
from .dashboard_cache import dashboard_cache
from .db import (
    DB_ERRORS, PROTECTED_DATABASES, READ_ONLY, USE_AZURE, ReadOnlyDatabaseError, connection, datamart_connection, fetch_all, fetch_one,
)
from .fr04 import router as fr04_router
from .indicadores import Population, SCENARIOS, read_dashboard
from .pacientes import router as patients_router
from .patient_directory import patient_directory
from .sesiones import router as sessions_router


DEFAULT_START = date(2022, 1, 1)
DEFAULT_END = date(2024, 12, 31)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if READ_ONLY and not USE_AZURE:
        await run_in_threadpool(patient_directory.get)
    yield


app = FastAPI(title="Musicoterapia BI", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(fr04_router)
app.include_router(patients_router)
app.include_router(sessions_router)


@app.middleware("http")
async def prevent_api_caching(request: Request, call_next):
    path = request.url.path
    if (READ_ONLY and path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and path not in {"/api/auth/login", "/api/auth/logout"}):
        response = JSONResponse(status_code=403, content={"detail": "La base está conectada en modo de solo lectura"})
    else:
        response = await call_next(request)
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    if request.url.path == "/api/auth/login":
        return JSONResponse(status_code=422, content={"detail": "Revisa el usuario y la contraseña ingresados"})
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(ReadOnlyDatabaseError)
async def read_only_error(request: Request, exc: ReadOnlyDatabaseError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.get("/api/salud")
def health():
    server_info_sql = "SELECT DB_NAME() AS base, CONNECTIONPROPERTY('net_transport') AS transporte"
    try:
        with connection() as conn:
            info = fetch_one(conn, server_info_sql)
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo conectar a SQL Server") from exc
    try:
        with datamart_connection() as conn:
            datamart = {"estado": "ok", **fetch_one(conn, server_info_sql)}
    except DB_ERRORS:
        datamart = {"estado": "no_disponible"}
    base = info["base"]
    mode = "solo_lectura" if READ_ONLY or base.casefold() in PROTECTED_DATABASES else "registro"
    return {"estado": "ok", "fuente": "transaccional", "base": base, "modo": mode, "transporte": info["transporte"],
            "datamart": datamart,
            "directorio_pacientes_disponible": patient_directory.snapshot is not None, "tableros_en_memoria": dashboard_cache.size()}


@app.get("/api/escenarios")
def scenarios(user: Annotated[UserProfile, Depends(require_dashboard)]):
    if user.alcance_datos != "GLOBAL":
        return [{"escenario": name, "pacientes": None, "incluidos": None} for name in SCENARIOS]
    try:
        with datamart_connection() as conn:
            return fetch_all(conn, queries.SCENARIOS)
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar el Datamart") from exc


@app.get("/api/tablero")
def dashboard(
    background_tasks: BackgroundTasks,
    user: Annotated[UserProfile, Depends(require_dashboard)],
    escenario: Literal["HIBRIDO", "SINTETICO_IA", "COMPARAR"] = Query(default="HIBRIDO"),
    poblacion: Population = Query(default="incluidos"),
    desde: date = Query(default=DEFAULT_START),
    hasta: date = Query(default=DEFAULT_END),
):
    if desde > hasta:
        raise HTTPException(status_code=422, detail="La fecha inicial supera la fecha final")
    if hasta == date.max:
        raise HTTPException(status_code=422, detail="La fecha final debe ser anterior a 9999-12-31")
    if (hasta - desde).days > 3660:
        raise HTTPException(status_code=422, detail="El intervalo no puede superar diez años")

    permissions = user.permisos
    reports = tuple(report for report, allowed in (
        ("RP01", permissions.ver_respuesta), ("RP02", permissions.ver_evaluaciones),
        ("RP03", permissions.ver_fr04), ("RP04", permissions.ver_agitacion),
    ) if allowed)
    owner = 0 if user.alcance_datos == "GLOBAL" else user.id_usuario_sistema

    results = {}
    for scenario in SCENARIOS if escenario == "COMPARAR" else (escenario,):
        key = (scenario, desde, hasta, poblacion, reports, owner)
        if READ_ONLY:
            snapshot = dashboard_cache.get_or_load(key, read_dashboard)
            if dashboard_cache.needs_refresh(snapshot):
                background_tasks.add_task(dashboard_cache.refresh, key, read_dashboard)
            results[scenario] = snapshot.response()
        else:
            results[scenario] = read_dashboard(*key)
    if escenario == "COMPARAR":
        return {"fuente": "Datamart", "escenarios": results}
    return results[escenario]


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
