-- Ejecutar después de las dimensiones y los hechos del Datamart.
USE [Datamart_Musicoterapia_Alzheimer];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;
BEGIN TRANSACTION;
GO

-- Dosis semanal: sumar tiempo efectivo en segundos y comparar con 30 minutos.
CREATE OR ALTER VIEW dbo.v_datosHechoAdherencia AS
WITH sesiones AS (
    SELECT p.id_paciente,
           lunes = DATEADD(day, -(DATEDIFF(day, '19000101', CAST(s.fecha_hora_inicio_sesion AS date)) % 7),
                           CAST(s.fecha_hora_inicio_sesion AS date)),
           segundos = COALESCE(DATEDIFF(second, p.fecha_hora_ingreso_paciente, p.fecha_hora_salida_paciente),0),
           clave = CAST(DATEDIFF(day, '19000101', CAST(s.fecha_hora_inicio_sesion AS date)) AS bigint)
                     * 10000000000 + s.id_sesion_musical
    FROM [BD_Musicoterapia_Alzheimer_20261127].dbo.participacion_sesion p
    JOIN [BD_Musicoterapia_Alzheimer_20261127].dbo.sesion_musical s ON s.id_sesion_musical = p.id_sesion_musical
    WHERE p.estado_participacion IN ('COMPLETA','INTERRUMPIDA')
), semana AS (
    SELECT id_paciente, lunes, COUNT(*) sesiones, SUM(segundos) segundos, MAX(clave) ultima_sesion
    FROM sesiones GROUP BY id_paciente,lunes
), vigencia AS (
    SELECT id_paciente, MIN(lunes) primera, MAX(lunes) ultima FROM semana GROUP BY id_paciente
), calendario AS (
    SELECT v.id_paciente, DATEADD(day, 7*g.value, v.primera) lunes
    FROM vigencia v CROSS APPLY GENERATE_SERIES(0, DATEDIFF(day,v.primera,v.ultima)/7) g
), acumulado AS (
    SELECT c.id_paciente,c.lunes,COALESCE(s.sesiones,0) sesiones,COALESCE(s.segundos,0) segundos,
           MAX(s.ultima_sesion) OVER (PARTITION BY c.id_paciente ORDER BY c.lunes ROWS UNBOUNDED PRECEDING) clave
    FROM calendario c LEFT JOIN semana s ON s.id_paciente=c.id_paciente AND s.lunes=c.lunes
)
SELECT a.id_paciente idPaciente, a.lunes idTiempo, sm.tipo_actividad idActividad,
       sm.modalidad_sesion idModalidad, sm.id_responsable idUsuarioSistema,
       a.sesiones SesionesPorSemana, a.segundos/60 MinutosPorSemana, 1 PacientesEnIntervencion,
       CASE WHEN a.sesiones >= 3 AND a.segundos >= 1800 THEN 1 ELSE 0 END PacientesQueCumplenDosis
FROM acumulado a
JOIN [BD_Musicoterapia_Alzheimer_20261127].dbo.sesion_musical sm ON sm.id_sesion_musical=a.clave%10000000000;
GO

-- Rectifica las medidas del hecho ya cargado en su grano paciente-semana.
SELECT p.KeyPaciente, t.KeyTiempo, COUNT(*) Sesiones, SUM(COALESCE(DATEDIFF(second,
       ps.fecha_hora_ingreso_paciente, ps.fecha_hora_salida_paciente),0)) Segundos
INTO #Dosis
FROM [BD_Musicoterapia_Alzheimer_20261127].dbo.participacion_sesion ps
JOIN [BD_Musicoterapia_Alzheimer_20261127].dbo.sesion_musical s ON s.id_sesion_musical=ps.id_sesion_musical
JOIN dbo.DimPaciente p ON p.idPaciente=ps.id_paciente
JOIN dbo.DimTiempo t ON t.idTiempo=DATEADD(day,
     -(DATEDIFF(day,'19000101',CAST(s.fecha_hora_inicio_sesion AS date))%7), CAST(s.fecha_hora_inicio_sesion AS date))
WHERE ps.estado_participacion IN ('COMPLETA','INTERRUMPIDA')
GROUP BY p.KeyPaciente,t.KeyTiempo
OPTION (MAXDOP 1,MAX_GRANT_PERCENT=0.5);

IF EXISTS (
    SELECT 1 FROM #Dosis d
    LEFT JOIN dbo.HechoAdherencia h ON h.KeyPaciente=d.KeyPaciente AND h.KeyTiempo=d.KeyTiempo
    WHERE h.KeyPaciente IS NULL OR h.SesionesPorSemana<>d.Sesiones
)
    THROW 51011, N'La dosis de la OLTP y las filas de HechoAdherencia no corresponden a la misma carga.', 1;

UPDATE h SET MinutosPorSemana=d.Segundos/60, PacientesQueCumplenDosis=k.cumple
FROM dbo.HechoAdherencia h
JOIN #Dosis d ON d.KeyPaciente=h.KeyPaciente AND d.KeyTiempo=h.KeyTiempo
CROSS APPLY (SELECT CASE WHEN d.Sesiones>=3 AND d.Segundos>=1800 THEN 1 ELSE 0 END) k(cumple)
WHERE h.MinutosPorSemana<>d.Segundos/60 OR h.PacientesQueCumplenDosis<>k.cumple
OPTION (MAXDOP 1,MAX_GRANT_PERCENT=0.5);

-- Agregados por paciente, día y responsable para K1, K6 y K7.
-- Conservan el denominador exacto y permiten el alcance por responsable.
IF OBJECT_ID(N'dbo.HechoRespuestaDiaria',N'U') IS NULL
BEGIN
    CREATE TABLE dbo.HechoRespuestaDiaria (
        KeyPaciente int NOT NULL REFERENCES dbo.DimPaciente(KeyPaciente),
        KeyTiempo int NOT NULL REFERENCES dbo.DimTiempo(KeyTiempo),
        KeyCuidador int NOT NULL REFERENCES dbo.DimCuidador(KeyCuidador),
        Positivas int NOT NULL,
        Neutras int NOT NULL,
        Negativas int NOT NULL,
        MinutosRespuesta decimal(19,2) NOT NULL,
        ConRespuesta int NOT NULL,
        RespuestasObservadas int NOT NULL,
        SinRespuesta int NOT NULL,
        PRIMARY KEY(KeyPaciente,KeyTiempo,KeyCuidador)
    );
END;

IF OBJECT_ID(N'dbo.HechoTurnoDiario',N'U') IS NULL
BEGIN
    CREATE TABLE dbo.HechoTurnoDiario (
        KeyPaciente int NOT NULL REFERENCES dbo.DimPaciente(KeyPaciente),
        KeyTiempo int NOT NULL REFERENCES dbo.DimTiempo(KeyTiempo),
        KeyCuidador int NOT NULL REFERENCES dbo.DimCuidador(KeyCuidador),
        Episodios int NOT NULL,
        TurnosValidos int NOT NULL,
        PRIMARY KEY(KeyPaciente,KeyTiempo,KeyCuidador)
    );
END;

-- Los puntajes individuales con momento y hora permiten volver a elegir
-- evaluaciones válidas cuando el usuario solicita un corte histórico.
IF OBJECT_ID(N'dbo.HechoPuntajeValido',N'U') IS NULL
BEGIN
    CREATE TABLE dbo.HechoPuntajeValido (
        KeyPaciente int NOT NULL REFERENCES dbo.DimPaciente(KeyPaciente),
        KeyTiempo int NOT NULL REFERENCES dbo.DimTiempo(KeyTiempo),
        Instrumento varchar(4) NOT NULL,
        IdEvaluacion bigint NOT NULL,
        FechaHora datetime2(0) NOT NULL,
        Momento varchar(24) NOT NULL,
        Puntaje decimal(9,2) NOT NULL,
        PRIMARY KEY(KeyPaciente,Instrumento,FechaHora,IdEvaluacion)
    );
END;

IF COL_LENGTH(N'dbo.HechoRespuestaDiaria', N'RespuestasObservadas') IS NULL
    ALTER TABLE dbo.HechoRespuestaDiaria ADD RespuestasObservadas int NOT NULL DEFAULT(0);
GO

DELETE FROM dbo.HechoRespuestaDiaria;
INSERT dbo.HechoRespuestaDiaria
    (KeyPaciente,KeyTiempo,KeyCuidador,Positivas,Neutras,Negativas,MinutosRespuesta,ConRespuesta,RespuestasObservadas,SinRespuesta)
SELECT p.KeyPaciente,t.KeyTiempo,c.KeyCuidador,
       SUM(CASE WHEN ps.experiencia_sesion='POSITIVA' THEN 1 ELSE 0 END),
       SUM(CASE WHEN ps.experiencia_sesion='NEUTRA' THEN 1 ELSE 0 END),
       SUM(CASE WHEN ps.experiencia_sesion='NEGATIVA' THEN 1 ELSE 0 END),
       SUM(CASE WHEN v.con_respuesta=1 THEN ps.minutos_hasta_primera_respuesta ELSE 0 END),
       SUM(v.con_respuesta),
       SUM(CASE WHEN ps.estado_respuesta_positiva='OBSERVADA' AND s.fecha_hora_inicio_musica IS NOT NULL
                THEN 1 ELSE 0 END),
       SUM(CASE WHEN ps.estado_respuesta_positiva='SIN_RESPUESTA' AND s.fecha_hora_inicio_musica IS NOT NULL
                THEN 1 ELSE 0 END)
FROM [BD_Musicoterapia_Alzheimer_20261127].dbo.participacion_sesion ps
JOIN [BD_Musicoterapia_Alzheimer_20261127].dbo.sesion_musical s ON s.id_sesion_musical=ps.id_sesion_musical
JOIN dbo.DimPaciente p ON p.idPaciente=ps.id_paciente
JOIN dbo.DimTiempo t ON t.idTiempo=CAST(s.fecha_hora_inicio_sesion AS date)
JOIN dbo.DimCuidador c ON c.idUsuarioSistema=COALESCE(s.id_responsable,0)
CROSS APPLY (SELECT CASE WHEN ps.estado_respuesta_positiva='OBSERVADA'
                             AND ps.fecha_hora_primera_respuesta>=s.fecha_hora_inicio_musica
                             AND ps.minutos_hasta_primera_respuesta>=0 THEN 1 ELSE 0 END) v(con_respuesta)
WHERE ps.estado_participacion IN ('COMPLETA','INTERRUMPIDA')
GROUP BY p.KeyPaciente,t.KeyTiempo,c.KeyCuidador
OPTION (MAXDOP 1,MAX_GRANT_PERCENT=0.5);

DELETE FROM dbo.HechoTurnoDiario;
INSERT dbo.HechoTurnoDiario (KeyPaciente,KeyTiempo,KeyCuidador,Episodios,TurnosValidos)
SELECT p.KeyPaciente,t.KeyTiempo,c.KeyCuidador,SUM(a.total_episodios),COUNT(*)
FROM [BD_Musicoterapia_Alzheimer_20261127].dbo.agitacion_turno a
JOIN dbo.DimPaciente p ON p.idPaciente=a.id_paciente
JOIN dbo.DimTiempo t ON t.idTiempo=a.fecha_turno
JOIN dbo.DimCuidador c ON c.idUsuarioSistema=COALESCE(a.id_responsable,0)
WHERE a.cobertura_observacion='OBSERVADO' AND a.total_episodios IS NOT NULL
GROUP BY p.KeyPaciente,t.KeyTiempo,c.KeyCuidador
OPTION (MAXDOP 1,MAX_GRANT_PERCENT=0.5);

DELETE FROM dbo.HechoPuntajeValido;
INSERT dbo.HechoPuntajeValido (KeyPaciente,KeyTiempo,Instrumento,IdEvaluacion,FechaHora,Momento,Puntaje)
SELECT p.KeyPaciente,t.KeyTiempo,i.codigo_instrumento,e.id_evaluacion_paciente,
       e.fecha_hora_evaluacion,e.momento_evaluacion,r.puntuacion_obtenida
FROM [BD_Musicoterapia_Alzheimer_20261127].dbo.evaluacion_paciente e
JOIN [BD_Musicoterapia_Alzheimer_20261127].dbo.resultado_evaluacion r ON r.id_evaluacion_paciente=e.id_evaluacion_paciente
JOIN [BD_Musicoterapia_Alzheimer_20261127].dbo.instrumento_evaluacion i ON i.id_instrumento_evaluacion=r.id_instrumento_evaluacion
JOIN dbo.DimPaciente p ON p.idPaciente=e.id_paciente
JOIN dbo.DimTiempo t ON t.idTiempo=CAST(e.fecha_hora_evaluacion AS date)
WHERE r.estado_puntaje='VALIDO' AND (
    (i.codigo_instrumento='MMSE' AND r.puntuacion_obtenida BETWEEN 0 AND 30)
    OR (e.condicion_evaluada='INTERVENCION' AND e.momento_evaluacion IN ('INICIAL','SEGUIMIENTO')
        AND ((i.codigo_instrumento='CMAI' AND r.puntuacion_obtenida BETWEEN 29 AND 203)
             OR (i.codigo_instrumento='CSDD' AND r.puntuacion_obtenida BETWEEN 0 AND 38)))
)
OPTION (MAXDOP 1,MAX_GRANT_PERCENT=0.5);

SELECT SUM(PacientesEnIntervencion) AS paciente_semanas,
       SUM(PacientesQueCumplenDosis) AS cumplen FROM dbo.HechoAdherencia;
SELECT SUM(Positivas) AS positivas,SUM(Positivas+Neutras+Negativas) AS valoradas,
       SUM(ConRespuesta) AS con_respuesta FROM dbo.HechoRespuestaDiaria;
SELECT Instrumento,COUNT_BIG(*) AS puntajes_validos FROM dbo.HechoPuntajeValido GROUP BY Instrumento;
SELECT SUM(TurnosValidos) AS turnos_validos FROM dbo.HechoTurnoDiario;
COMMIT TRANSACTION;
