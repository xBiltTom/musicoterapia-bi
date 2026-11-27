"""Cálculo y presentación de K1 a K7 sobre el Datamart."""

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException

from . import queries
from .db import DB_ERRORS, datamart_connection, fetch_all, fetch_one, sqlstate


Scenario = Literal["HIBRIDO", "SINTETICO_IA"]
Population = Literal["incluidos", "todos"]
SCENARIOS = ("HIBRIDO", "SINTETICO_IA")
logger = logging.getLogger(__name__)


def monday(day):
    return day - timedelta(days=day.weekday())


def percent(numerator, denominator):
    return 100 * Decimal(numerator) / denominator if denominator else None


def number(value):
    return float(round(value, 4)) if value is not None else None


def status(indicator, value):
    if value is None:
        return "sin_datos"
    if indicator == "k6":
        return "verde" if value <= 3 else "ambar" if value <= 5 else "rojo"
    green, amber = {
        "k1": (70, 50), "k2": (6, 3), "k3": (4, 2), "k4": (80, 60), "k5": (24, 18),
        "k7": (1, Decimal("0.5")),
    }[indicator]
    return "verde" if value >= green else "ambar" if value >= amber else "rojo"


def response_metrics(months):
    fields = ("positivas", "neutras", "negativas", "minutos_respuesta", "con_respuesta",
              "respuestas_observadas", "sin_respuesta")
    sums = {field: sum(month[field] for month in months) for field in fields}
    valid = sums["positivas"] + sums["neutras"] + sums["negativas"]
    positive_rate = percent(sums["positivas"], valid)
    observed = sums["respuestas_observadas"] + sums["sin_respuesta"]
    response_minutes = sums["minutos_respuesta"] / sums["con_respuesta"] if sums["con_respuesta"] else None
    return {
        "k1": {
            "tasa_positiva": number(positive_rate), "estado": status("k1", positive_rate),
            "positivas": sums["positivas"], "neutras": sums["neutras"], "negativas": sums["negativas"],
            "participaciones_validas": valid,
        },
        "k6": {
            "tiempo_promedio_minutos": number(response_minutes), "estado": status("k6", response_minutes),
            "con_respuesta": sums["con_respuesta"], "sin_respuesta": sums["sin_respuesta"],
            "observaciones_validas": observed,
            "tasa_sin_respuesta": number(percent(sums["sin_respuesta"], observed)),
        },
        "respuesta_mensual": [
            {"mes": row["mes"], "positivas": row["positivas"], "participaciones_validas": bases,
             "tasa_positiva": number(percent(row["positivas"], bases))}
            for row in months if (bases := row["positivas"] + row["neutras"] + row["negativas"])
        ],
    }


def clinical_metrics(pairs, mmse):
    values = {row["instrumento"]: row for row in pairs}
    cmai, csdd = values.get("CMAI", {}), values.get("CSDD", {})
    cmai_pairs, csdd_pairs = cmai.get("pares", 0), csdd.get("pares", 0)
    cmai_reduction, csdd_reduction = cmai.get("reduccion"), csdd.get("reduccion")
    responders = cmai.get("respondedores", 0)
    above_cut, crossings = csdd.get("basales_sobre_corte", 0), csdd.get("cruces_corte", 0)
    return {
        "k2": {
            "reduccion_promedio": number(cmai_reduction), "estado": status("k2", cmai_reduction),
            "pacientes_con_par": cmai_pairs, "respondedores": responders,
            "tasa_respondedores": number(percent(responders, cmai_pairs)),
        },
        "k3": {
            "reduccion_promedio": number(csdd_reduction), "estado": status("k3", csdd_reduction),
            "pacientes_con_par": csdd_pairs, "basales_sobre_corte": above_cut, "cruces_corte": crossings,
            "tasa_cruce_corte": number(percent(crossings, above_cut)),
        },
        "k5": {
            **mmse, "promedio": number(mmse["promedio"]), "variacion": number(mmse["variacion"]),
            "estado": status("k5", mmse["promedio"]),
        },
    }


def read_adherence(conn, scenario, population, start, end):
    record = fetch_one(conn, queries.ADHERENCE, (scenario, population == "incluidos", monday(start), monday(end)))
    rate = percent(record["cumplen"], record["paciente_semanas"])
    return {**record, "tasa_adherencia": number(rate), "estado": status("k4", rate)}


def read_dashboard(scenario, start, end, population, reports, owner):
    result = {"fuente": "Datamart", "filtros": {"escenario": scenario, "desde": start, "hasta": end,
                                               "poblacion": population, "alcance": "propios" if owner else "global"}}
    params = (scenario, population == "incluidos", start, end)
    try:
        with datamart_connection() as conn:
            if "RP01" in reports:
                result.update(response_metrics(fetch_all(conn, queries.MONTHLY_RESPONSE, (*params, owner, owner))))
            if "RP02" in reports:
                result.update(clinical_metrics(fetch_all(conn, queries.PAIRED_SCORES, params),
                                               fetch_one(conn, queries.MMSE, params)))
            if "RP03" in reports:
                result["k4"] = read_adherence(conn, scenario, population, start, end)
            if "RP04" in reports:
                row = fetch_one(conn, queries.AGITATION, (*params, owner, owner))
                reduction = row.pop("reduccion")
                result["k7"] = {**row, "reduccion_promedio": number(reduction), "estado": status("k7", reduction)}
    except DB_ERRORS as exc:
        state = sqlstate(exc)
        logger.warning("No se pudieron consultar los indicadores (SQLSTATE %s)", state)
        detail = "El Datamart superó el tiempo de espera" if state in {"HYT00", "HYT01"} else "No se pudo consultar el Datamart"
        raise HTTPException(status_code=503, detail=detail) from exc
    return result
