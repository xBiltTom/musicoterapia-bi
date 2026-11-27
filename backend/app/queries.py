"""Consultas parametrizadas de los indicadores dimensionales."""

SCENARIOS = """
SELECT Escenario AS escenario, COUNT_BIG(*) AS pacientes,
       SUM(CASE WHEN Inclusion=N'Incluido' THEN 1 ELSE 0 END) AS incluidos
FROM dbo.DimPaciente
GROUP BY Escenario
ORDER BY Escenario
"""

MONTHLY_RESPONSE = """
SELECT t.Mes AS mes, SUM(h.Positivas) AS positivas, SUM(h.Neutras) AS neutras,
       SUM(h.Negativas) AS negativas, SUM(h.MinutosRespuesta) AS minutos_respuesta,
       SUM(h.ConRespuesta) AS con_respuesta, SUM(h.RespuestasObservadas) AS respuestas_observadas,
       SUM(h.SinRespuesta) AS sin_respuesta
FROM dbo.HechoRespuestaDiaria h
JOIN dbo.DimPaciente p ON p.KeyPaciente=h.KeyPaciente
JOIN dbo.DimTiempo t ON t.KeyTiempo=h.KeyTiempo
JOIN dbo.DimCuidador c ON c.KeyCuidador=h.KeyCuidador
WHERE p.Escenario=? AND (?=0 OR p.Inclusion=N'Incluido')
  AND t.idTiempo BETWEEN ? AND ? AND (?=0 OR c.idUsuarioSistema=?)
GROUP BY t.Mes
ORDER BY t.Mes
OPTION (MAXDOP 1, MAX_GRANT_PERCENT=1)
"""

PAIRED_SCORES = """
WITH seguimientos AS (
    SELECT h.KeyPaciente,h.Instrumento,h.FechaHora,h.Puntaje,
           ROW_NUMBER() OVER (PARTITION BY h.KeyPaciente,h.Instrumento
                              ORDER BY h.FechaHora DESC,h.IdEvaluacion DESC) orden
    FROM dbo.HechoPuntajeValido h
    JOIN dbo.DimPaciente p ON p.KeyPaciente=h.KeyPaciente
    JOIN dbo.DimTiempo t ON t.KeyTiempo=h.KeyTiempo
    WHERE p.Escenario=? AND (?=0 OR p.Inclusion=N'Incluido')
      AND t.idTiempo BETWEEN ? AND ? AND h.Instrumento IN('CMAI','CSDD') AND h.Momento='SEGUIMIENTO'
)
SELECT s.Instrumento AS instrumento, COUNT_BIG(*) AS pares, AVG(b.Puntaje-s.Puntaje) AS reduccion,
       SUM(CASE WHEN b.Puntaje-s.Puntaje>=6 THEN 1 ELSE 0 END) AS respondedores,
       SUM(CASE WHEN b.Puntaje>10 THEN 1 ELSE 0 END) AS basales_sobre_corte,
       SUM(CASE WHEN b.Puntaje>10 AND s.Puntaje<=10 THEN 1 ELSE 0 END) AS cruces_corte
FROM seguimientos s
CROSS APPLY (
    SELECT TOP (1) h.Puntaje
    FROM dbo.HechoPuntajeValido h
    WHERE h.KeyPaciente=s.KeyPaciente AND h.Instrumento=s.Instrumento
      AND h.Momento='INICIAL' AND h.FechaHora<s.FechaHora
    ORDER BY h.FechaHora,h.IdEvaluacion
) b
WHERE s.orden=1
GROUP BY s.Instrumento
OPTION (MAXDOP 1, MAX_GRANT_PERCENT=1)
"""

ADHERENCE = """
SELECT COALESCE(SUM(h.PacientesEnIntervencion),0) AS paciente_semanas,
       COALESCE(SUM(h.PacientesQueCumplenDosis),0) AS cumplen
FROM dbo.HechoAdherencia h
JOIN dbo.DimPaciente p ON p.KeyPaciente=h.KeyPaciente
JOIN dbo.DimTiempo t ON t.KeyTiempo=h.KeyTiempo
WHERE p.Escenario=? AND (?=0 OR p.Inclusion=N'Incluido') AND t.idTiempo BETWEEN ? AND ?
OPTION (MAXDOP 1, MAX_GRANT_PERCENT=1)
"""

MMSE = """
WITH puntajes AS (
    SELECT h.Puntaje,t.idTiempo,
           FIRST_VALUE(h.Puntaje) OVER (PARTITION BY h.KeyPaciente ORDER BY h.FechaHora,h.IdEvaluacion) primero,
           MIN(t.idTiempo) OVER (PARTITION BY h.KeyPaciente) fecha_primera,
           ROW_NUMBER() OVER (PARTITION BY h.KeyPaciente ORDER BY h.FechaHora DESC,h.IdEvaluacion DESC) orden
    FROM dbo.HechoPuntajeValido h
    JOIN dbo.DimPaciente p ON p.KeyPaciente=h.KeyPaciente
    JOIN dbo.DimTiempo t ON t.KeyTiempo=h.KeyTiempo
    WHERE p.Escenario=? AND (?=0 OR p.Inclusion=N'Incluido')
      AND t.idTiempo BETWEEN ? AND ? AND h.Instrumento='MMSE'
)
SELECT COUNT_BIG(*) AS pacientes, AVG(Puntaje) AS promedio,
       AVG(CASE WHEN idTiempo>fecha_primera THEN Puntaje-primero END) AS variacion,
       COUNT_BIG(CASE WHEN idTiempo>fecha_primera THEN 1 END) AS pacientes_con_variacion
FROM puntajes
WHERE orden=1
OPTION (MAXDOP 1, MAX_GRANT_PERCENT=1)
"""

AGITATION = """
WITH trimestres AS (
    SELECT h.KeyPaciente,DATETRUNC(quarter,t.idTiempo) trimestre,
           CAST(SUM(h.Episodios) AS decimal(19,9))/SUM(h.TurnosValidos) tasa,
           SUM(h.TurnosValidos) turnos
    FROM dbo.HechoTurnoDiario h
    JOIN dbo.DimPaciente p ON p.KeyPaciente=h.KeyPaciente
    JOIN dbo.DimTiempo t ON t.KeyTiempo=h.KeyTiempo
    JOIN dbo.DimCuidador c ON c.KeyCuidador=h.KeyCuidador
    WHERE p.Escenario=? AND (?=0 OR p.Inclusion=N'Incluido')
      AND t.idTiempo BETWEEN ? AND ? AND (?=0 OR c.idUsuarioSistema=?)
    GROUP BY h.KeyPaciente,DATETRUNC(quarter,t.idTiempo)
), extremos AS (
    SELECT *, MIN(trimestre) OVER (PARTITION BY KeyPaciente) primero,
              MAX(trimestre) OVER (PARTITION BY KeyPaciente) ultimo
    FROM trimestres
), tasas AS (
    SELECT KeyPaciente,
           MAX(CASE WHEN trimestre=primero THEN tasa END) inicial,
           MAX(CASE WHEN trimestre=ultimo THEN tasa END) reciente,
           SUM(turnos) turnos
    FROM extremos
    WHERE primero<>ultimo AND trimestre IN (primero,ultimo)
    GROUP BY KeyPaciente
)
SELECT COUNT_BIG(*) AS pacientes_comparables, AVG(inicial) AS tasa_inicial,
       AVG(reciente) AS tasa_reciente, AVG(inicial-reciente) AS reduccion,
       COALESCE(SUM(turnos),0) AS turnos_comparados
FROM tasas
OPTION (MAXDOP 1, MAX_GRANT_PERCENT=1)
"""
