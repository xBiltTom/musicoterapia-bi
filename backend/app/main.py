"""API del tablero inicial sobre la base transaccional."""

from datetime import date
from pathlib import Path

import pyodbc
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import queries
from .db import connection, fetch_all, fetch_one
from .fr04 import router as fr04_router


app = FastAPI(title="Musicoterapia BI", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "PUT"],
    allow_headers=["*"],
)
app.include_router(fr04_router)


def percentage(numerator: int, denominator: int):
    return round(100 * numerator / denominator, 2) if denominator else None


@app.get("/api/salud")
def health():
    try:
        with connection() as conn:
            fetch_one(conn, "SELECT 1 AS ok")
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail="No se pudo conectar a SQL Server") from exc
    return {"estado": "ok", "fuente": "transaccional"}


@app.get("/api/escenarios")
def scenarios():
    try:
        with connection() as conn:
            return fetch_all(conn, queries.SCENARIOS)
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar SQL Server") from exc


@app.get("/api/tablero")
def dashboard(
    escenario: str = Query(default="HIBRIDO"),
    desde: date = Query(default=date(2022, 1, 1)),
    hasta: date = Query(default=date(2024, 12, 31)),
):
    if desde > hasta:
        raise HTTPException(status_code=422, detail="La fecha inicial supera la fecha final")
    if (hasta - desde).days > 3660:
        raise HTTPException(status_code=422, detail="El intervalo no puede superar diez años")

    try:
        with connection() as conn:
            allowed = {row["escenario"] for row in fetch_all(conn, queries.SCENARIOS)}
            if escenario not in allowed:
                raise HTTPException(status_code=422, detail="Escenario desconocido")

            params = (escenario, desde, hasta)
            k1 = fetch_one(conn, queries.K1, params)
            monthly = fetch_all(conn, queries.K1_MONTHLY, params)
            pair_params = (escenario, hasta, escenario, desde, hasta)
            k2 = fetch_one(conn, queries.K2, pair_params)
            k3 = fetch_one(conn, queries.K3, pair_params)
    except pyodbc.Error as exc:
        raise HTTPException(status_code=503, detail="No se pudo consultar SQL Server") from exc

    valid = int(k1["participaciones_validas"] or 0)
    positives = int(k1["positivas"] or 0)
    cmai_pairs = int(k2["pacientes_con_par"] or 0)
    csdd_pairs = int(k3["pacientes_con_par"] or 0)
    csdd_eligible = int(k3["basales_sobre_corte"] or 0)

    return {
        "fuente": "base transaccional",
        "filtros": {"escenario": escenario, "desde": desde, "hasta": hasta},
        "k1": {
            "tasa_positiva": percentage(positives, valid),
            "positivas": positives,
            "neutras": int(k1["neutras"] or 0),
            "negativas": int(k1["negativas"] or 0),
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
