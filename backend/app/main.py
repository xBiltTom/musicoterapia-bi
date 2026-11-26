"""API del tablero inicial sobre la base transaccional."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import date
from pathlib import Path

import pyodbc
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import queries
from .auth import require_dashboard, router as auth_router
from .dashboard_cache import dashboard_cache
from .db import PROTECTED_DATABASE, READ_ONLY, ReadOnlyDatabaseError, connection, fetch_all, fetch_one, sqlstate
from .fr04 import router as fr04_router
from .pacientes import router as patients_router
from .patient_directory import patient_directory
from .sesiones import router as sessions_router


DEFAULT_START = date(2022, 1, 1)
DEFAULT_END = date(2024, 12, 31)
logger = logging.getLogger(__name__)


async def warm_dashboard():
    scenarios = ("HIBRIDO", "SINTETICO_IA")
    for attempt in range(2):
        if attempt > 0:
            await asyncio.sleep(30)
        for scenario in scenarios:
            try:
                await run_in_threadpool(dashboard_cache.get_or_load, (scenario, DEFAULT_START, DEFAULT_END), read_dashboard)
            except HTTPException as exc:
                if exc.status_code == 503:
                    break
        else:
            return


@asynccontextmanager
async def lifespan(app: FastAPI):
    prewarm = None
    if READ_ONLY:
        await run_in_threadpool(patient_directory.get)
        prewarm = asyncio.create_task(warm_dashboard())
    try:
        yield
    finally:
        if prewarm is not None:
            prewarm.cancel()
            with suppress(asyncio.CancelledError):
                await prewarm


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


def percentage(numerator: int, denominator: int):
    return round(100 * numerator / denominator, 2) if denominator else None


@app.get("/api/salud")
def health():
    try:
        with connection() as conn:
            info = fetch_one(conn, "SELECT DB_NAME() AS base, CONNECTIONPROPERTY('net_transport') AS transporte")
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail="No se pudo conectar a SQL Server") from exc
    base = info["base"]
    mode = "solo_lectura" if READ_ONLY or base.casefold() == PROTECTED_DATABASE.casefold() else "registro"
    return {"estado": "ok", "fuente": "transaccional", "base": base, "modo": mode, "transporte": info["transporte"],
            "directorio_pacientes_disponible": patient_directory.snapshot is not None, "tableros_en_memoria": dashboard_cache.size()}


@app.get("/api/escenarios", dependencies=[Depends(require_dashboard)])
def scenarios():
    snapshot = patient_directory.snapshot if READ_ONLY else None
    if snapshot is not None:
        return [{"escenario": scenario, "pacientes": len(rows)} for scenario, rows in sorted(snapshot.patients.items())]
    try:
        with connection() as conn:
            return fetch_all(conn, queries.SCENARIOS)
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar SQL Server") from exc


@app.get("/api/tablero", dependencies=[Depends(require_dashboard)])
def dashboard(
    background_tasks: BackgroundTasks,
    escenario: str = Query(default="HIBRIDO"),
    desde: date = Query(default=DEFAULT_START),
    hasta: date = Query(default=DEFAULT_END),
):
    if desde > hasta:
        raise HTTPException(status_code=422, detail="La fecha inicial supera la fecha final")
    if hasta == date.max:
        raise HTTPException(status_code=422, detail="La fecha final debe ser anterior a 9999-12-31")
    if (hasta - desde).days > 3660:
        raise HTTPException(status_code=422, detail="El intervalo no puede superar diez años")

    if READ_ONLY:
        key = (escenario, desde, hasta)
        snapshot = dashboard_cache.get_or_load(key, read_dashboard)
        if dashboard_cache.needs_refresh(snapshot):
            background_tasks.add_task(dashboard_cache.refresh, key, read_dashboard)
        return snapshot.response()
    return read_dashboard(escenario, desde, hasta)


def read_dashboard(escenario, desde, hasta):
    try:
        with connection() as conn:
            patients = queries.scenario_patients(conn, escenario)
            if not patients:
                raise HTTPException(status_code=422, detail="Escenario desconocido")

            monthly = queries.monthly_experience(conn, patients, desde, hasta)
            paired = queries.paired_scores(conn, patients, desde, hasta)
            k2, k3 = paired["CMAI"], paired["CSDD"]
    except pyodbc.Error as exc:
        state = sqlstate(exc)
        logger.warning("No se pudieron consultar los indicadores (SQLSTATE %s)", state)
        detail = "No se pudo consultar SQL Server"
        if state in {"HYT00", "HYT01"}:
            detail = "SQL Server superó el tiempo de espera al calcular los indicadores"
        raise HTTPException(status_code=503, detail=detail) from exc

    valid = sum(row["participaciones_validas"] for row in monthly)
    positives = sum(row["positivas"] for row in monthly)
    cmai_pairs = int(k2["pacientes_con_par"] or 0)
    csdd_pairs = int(k3["pacientes_con_par"] or 0)
    csdd_eligible = int(k3["basales_sobre_corte"] or 0)

    return {
        "fuente": "base transaccional",
        "filtros": {"escenario": escenario, "desde": desde, "hasta": hasta},
        "k1": {
            "tasa_positiva": percentage(positives, valid),
            "positivas": positives,
            "neutras": sum(row["neutras"] for row in monthly),
            "negativas": sum(row["negativas"] for row in monthly),
            "participaciones_validas": valid,
        },
        "k2": {
            "reduccion_promedio": round(k2["reduccion_promedio"], 2) if k2["reduccion_promedio"] is not None else None,
            "pacientes_con_par": cmai_pairs,
            "respondedores": int(k2["respondedores"] or 0),
            "tasa_respondedores": percentage(int(k2["respondedores"] or 0), cmai_pairs),
        },
        "k3": {
            "reduccion_promedio": round(k3["reduccion_promedio"], 2) if k3["reduccion_promedio"] is not None else None,
            "pacientes_con_par": csdd_pairs,
            "basales_sobre_corte": csdd_eligible,
            "cruces_corte": int(k3["cruces_corte"] or 0),
            "tasa_cruce_corte": percentage(int(k3["cruces_corte"] or 0), csdd_eligible),
        },
        "respuesta_mensual": [
            {
                "mes": row["mes"],
                "positivas": int(row["positivas"]),
                "participaciones_validas": int(row["participaciones_validas"]),
                "tasa_positiva": percentage(int(row["positivas"]), int(row["participaciones_validas"])),
            }
            for row in monthly
        ],
    }


FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
