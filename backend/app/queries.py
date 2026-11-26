"""Consultas directas a las tablas transaccionales.

Todas reciben parametros posicionales. No se crean vistas, tablas ni data marts.
"""

SCENARIOS = """
SELECT escenario, COUNT_BIG(*) AS pacientes
FROM dbo.paciente
GROUP BY escenario
ORDER BY escenario
"""

K1 = """
SELECT
    SUM(CASE WHEN ps.experiencia_sesion = 'POSITIVA' THEN 1 ELSE 0 END) AS positivas,
    SUM(CASE WHEN ps.experiencia_sesion = 'NEUTRA' THEN 1 ELSE 0 END) AS neutras,
    SUM(CASE WHEN ps.experiencia_sesion = 'NEGATIVA' THEN 1 ELSE 0 END) AS negativas,
    COUNT_BIG(*) AS participaciones_validas
FROM dbo.participacion_sesion AS ps
JOIN dbo.paciente AS p ON p.id_paciente = ps.id_paciente
JOIN dbo.sesion_musical AS s ON s.id_sesion_musical = ps.id_sesion_musical
WHERE p.escenario = ?
  AND s.fecha_hora_inicio_sesion >= ?
  AND s.fecha_hora_inicio_sesion < DATEADD(day, 1, CAST(? AS date))
  AND ps.experiencia_sesion IN ('POSITIVA', 'NEUTRA', 'NEGATIVA')
"""

K1_MONTHLY = """
SELECT
    CONVERT(char(7), s.fecha_hora_inicio_sesion, 120) AS mes,
    SUM(CASE WHEN ps.experiencia_sesion = 'POSITIVA' THEN 1 ELSE 0 END) AS positivas,
    COUNT_BIG(*) AS participaciones_validas
FROM dbo.participacion_sesion AS ps
JOIN dbo.paciente AS p ON p.id_paciente = ps.id_paciente
JOIN dbo.sesion_musical AS s ON s.id_sesion_musical = ps.id_sesion_musical
WHERE p.escenario = ?
  AND s.fecha_hora_inicio_sesion >= ?
  AND s.fecha_hora_inicio_sesion < DATEADD(day, 1, CAST(? AS date))
  AND ps.experiencia_sesion IN ('POSITIVA', 'NEUTRA', 'NEGATIVA')
GROUP BY CONVERT(char(7), s.fecha_hora_inicio_sesion, 120)
ORDER BY mes
"""


def paired_score_query(instrument: str, min_score: int, max_score: int, crossed: bool = False) -> str:
    """Primera evaluacion inicial y ultimo seguimiento valido en el periodo."""
    extra = (
        ", SUM(CASE WHEN basal.puntuacion > 10 THEN 1 ELSE 0 END) AS basales_sobre_corte"
        ", SUM(CASE WHEN basal.puntuacion > 10 AND seguimiento.puntuacion <= 10 "
        "THEN 1 ELSE 0 END) AS cruces_corte"
        if crossed
        else ", SUM(CASE WHEN basal.puntuacion - seguimiento.puntuacion >= 6 "
        "THEN 1 ELSE 0 END) AS respondedores"
    )
    return f"""
WITH basal AS (
    SELECT e.id_paciente, e.fecha_hora_evaluacion AS fecha,
           r.puntuacion_obtenida AS puntuacion,
           ROW_NUMBER() OVER (
               PARTITION BY e.id_paciente
               ORDER BY e.fecha_hora_evaluacion, e.id_evaluacion_paciente
           ) AS orden
    FROM dbo.evaluacion_paciente AS e
    JOIN dbo.resultado_evaluacion AS r
      ON r.id_evaluacion_paciente = e.id_evaluacion_paciente
    JOIN dbo.instrumento_evaluacion AS i
      ON i.id_instrumento_evaluacion = r.id_instrumento_evaluacion
    JOIN dbo.paciente AS p ON p.id_paciente = e.id_paciente
    WHERE p.escenario = ? AND i.codigo_instrumento = '{instrument}'
      AND e.momento_evaluacion = 'INICIAL'
      AND e.fecha_hora_evaluacion < DATEADD(day, 1, CAST(? AS date))
      AND r.puntuacion_obtenida BETWEEN {min_score} AND {max_score}
), seguimiento AS (
    SELECT e.id_paciente, e.fecha_hora_evaluacion AS fecha,
           r.puntuacion_obtenida AS puntuacion,
           ROW_NUMBER() OVER (
               PARTITION BY e.id_paciente
               ORDER BY e.fecha_hora_evaluacion DESC, e.id_evaluacion_paciente DESC
           ) AS orden
    FROM dbo.evaluacion_paciente AS e
    JOIN dbo.resultado_evaluacion AS r
      ON r.id_evaluacion_paciente = e.id_evaluacion_paciente
    JOIN dbo.instrumento_evaluacion AS i
      ON i.id_instrumento_evaluacion = r.id_instrumento_evaluacion
    JOIN dbo.paciente AS p ON p.id_paciente = e.id_paciente
    WHERE p.escenario = ? AND i.codigo_instrumento = '{instrument}'
      AND e.momento_evaluacion = 'SEGUIMIENTO'
      AND e.fecha_hora_evaluacion >= ?
      AND e.fecha_hora_evaluacion < DATEADD(day, 1, CAST(? AS date))
      AND r.puntuacion_obtenida BETWEEN {min_score} AND {max_score}
)
SELECT COUNT_BIG(*) AS pacientes_con_par,
       AVG(CAST(basal.puntuacion - seguimiento.puntuacion AS float)) AS reduccion_promedio
       {extra}
FROM basal
JOIN seguimiento ON seguimiento.id_paciente = basal.id_paciente
WHERE basal.orden = 1 AND seguimiento.orden = 1
  AND basal.fecha < seguimiento.fecha
"""


K2 = paired_score_query("CMAI", 29, 203)
K3 = paired_score_query("CSDD", 0, 38, crossed=True)
