"""Consultas directas a las tablas transaccionales.

Todas reciben parametros posicionales. No se crean vistas, tablas ni data marts.
"""

from collections import Counter, defaultdict
from contextlib import closing

SCENARIOS = """
SELECT escenario, COUNT_BIG(*) AS pacientes
FROM dbo.paciente
GROUP BY escenario
ORDER BY escenario
"""

def scenario_patients(conn, scenario):
    with closing(conn.cursor()) as cursor:
        cursor.execute("SELECT id_paciente FROM dbo.paciente WHERE escenario = ?", scenario)
        return {row[0] for row in cursor.fetchall()}


def monthly_experience(conn, patients, start, end):
    """Agrupa K1 sin ejecutar la unión masiva de tres tablas en SQL Server Express."""
    counts = defaultdict(Counter)
    with closing(conn.cursor()) as cursor:
        cursor.execute("""
            SELECT id_sesion_musical, CONVERT(char(7), fecha_hora_inicio_sesion, 120)
            FROM dbo.sesion_musical
            WHERE fecha_hora_inicio_sesion >= ? AND fecha_hora_inicio_sesion < DATEADD(day, 1, CAST(? AS date))
        """, start, end)
        months = {row[0]: row[1] for row in cursor.fetchall()}
        if not months:
            return []
        cursor.execute("""
            SELECT id_sesion_musical, id_paciente, experiencia_sesion
            FROM dbo.participacion_sesion
            WHERE experiencia_sesion IN ('POSITIVA', 'NEUTRA', 'NEGATIVA')
        """)
        while batch := cursor.fetchmany(8_192):
            for session_id, patient_id, experience in batch:
                month = months.get(session_id)
                if month and patient_id in patients:
                    counts[month][experience.strip().upper()] += 1

    return [{"mes": month, "positivas": values["POSITIVA"], "neutras": values["NEUTRA"],
             "negativas": values["NEGATIVA"], "participaciones_validas": sum(values.values())}
            for month, values in sorted(counts.items())]


def summarize_scores(initial, followup):
    count = 0
    total = 0
    responders = 0
    above_cut = 0
    crossings = 0
    for patient, (baseline_order, baseline_score) in initial.items():
        latest = followup.get(patient)
        if latest is None or baseline_order[0] >= latest[0][0]:
            continue
        score = latest[1]
        change = baseline_score - score
        count += 1
        total += change
        responders += change >= 6
        above_cut += baseline_score > 10
        crossings += baseline_score > 10 and score <= 10
    return {"pacientes_con_par": count, "reduccion_promedio": float(total / count) if count else None,
            "respondedores": responders, "basales_sobre_corte": above_cut, "cruces_corte": crossings}


def paired_scores(conn, patients, start, end):
    """Compara el primer basal válido con el último seguimiento del periodo."""
    ranges = {"CMAI": (29, 203), "CSDD": (0, 38)}
    initial = {code: {} for code in ranges}
    followup = {code: {} for code in ranges}
    with closing(conn.cursor()) as cursor:
        cursor.execute("""SELECT id_instrumento_evaluacion, codigo_instrumento
                          FROM dbo.instrumento_evaluacion WHERE codigo_instrumento IN ('CMAI', 'CSDD')""")
        instruments = {row[0]: row[1].strip().upper() for row in cursor.fetchall()}
        cursor.execute("""
            SELECT id_evaluacion_paciente, id_paciente, fecha_hora_evaluacion, momento_evaluacion
            FROM dbo.evaluacion_paciente
            WHERE fecha_hora_evaluacion < DATEADD(day, 1, CAST(? AS date))
              AND (momento_evaluacion = 'INICIAL' OR (momento_evaluacion = 'SEGUIMIENTO' AND fecha_hora_evaluacion >= ?))
        """, end, start)
        evaluations = {}
        while batch := cursor.fetchmany(8_192):
            for evaluation_id, patient, evaluated_at, phase in batch:
                if patient in patients:
                    evaluations[evaluation_id] = (patient, evaluated_at, phase.strip().upper() == "INICIAL")

        for instrument_id, code in instruments.items():
            minimum, maximum = ranges[code]
            cursor.execute("""
                SELECT id_evaluacion_paciente, puntuacion_obtenida, id_resultado_evaluacion
                FROM dbo.resultado_evaluacion
                WHERE id_instrumento_evaluacion = ? AND estado_puntaje = 'VALIDO' AND puntuacion_obtenida BETWEEN ? AND ?
            """, instrument_id, minimum, maximum)
            while batch := cursor.fetchmany(8_192):
                for evaluation_id, score, result_id in batch:
                    evaluation = evaluations.get(evaluation_id)
                    if evaluation is None:
                        continue
                    patient, evaluated_at, is_initial = evaluation
                    destination = initial[code] if is_initial else followup[code]
                    order = (evaluated_at, evaluation_id, result_id if is_initial else -result_id)
                    previous = destination.get(patient)
                    if previous is None or (order < previous[0] if is_initial else order > previous[0]):
                        destination[patient] = (order, score)

    return {code: summarize_scores(initial[code], followup[code]) for code in ranges}
