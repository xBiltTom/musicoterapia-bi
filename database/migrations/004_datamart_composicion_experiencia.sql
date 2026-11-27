-- Desglose diario de experiencias para el tablero, por escenario.
-- Ejecutar después de cargar DimPaciente, DimTiempo y HechoSesiones.
USE [Datamart_Musicoterapia_Alzheimer];
GO
SET NOCOUNT ON;
SET XACT_ABORT ON;

BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.HechoComposicionExperiencia', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.HechoComposicionExperiencia (
        Escenario NVARCHAR(60) NOT NULL,
        KeyTiempo INT NOT NULL,
        ParticipacionesNeutras INT NOT NULL,
        ParticipacionesNegativas INT NOT NULL,
        CONSTRAINT PK_HechoComposicionExperiencia PRIMARY KEY (Escenario, KeyTiempo),
        CONSTRAINT FK_HechoComposicionExperiencia_Tiempo FOREIGN KEY (KeyTiempo) REFERENCES dbo.DimTiempo (KeyTiempo),
        CONSTRAINT CK_HechoComposicionExperiencia_Conteos CHECK (
            ParticipacionesNeutras >= 0 AND ParticipacionesNegativas >= 0
        )
    );
END;

DELETE FROM dbo.HechoComposicionExperiencia;

INSERT INTO dbo.HechoComposicionExperiencia
    (Escenario, KeyTiempo, ParticipacionesNeutras, ParticipacionesNegativas)
SELECT p.Escenario, t.KeyTiempo,
       SUM(CASE WHEN ps.experiencia_sesion = 'NEUTRA' THEN 1 ELSE 0 END),
       SUM(CASE WHEN ps.experiencia_sesion = 'NEGATIVA' THEN 1 ELSE 0 END)
FROM [BD_Musicoterapia_Alzheimer_20261127].dbo.participacion_sesion AS ps
JOIN [BD_Musicoterapia_Alzheimer_20261127].dbo.sesion_musical AS s
    ON s.id_sesion_musical = ps.id_sesion_musical
JOIN dbo.DimPaciente AS p ON p.idPaciente = ps.id_paciente
JOIN dbo.DimTiempo AS t ON t.idTiempo = CAST(s.fecha_hora_inicio_sesion AS date)
WHERE ps.estado_participacion <> 'AUSENTE' AND ps.experiencia_sesion IN ('NEUTRA', 'NEGATIVA')
GROUP BY p.Escenario, t.KeyTiempo
OPTION (MAXDOP 1, MAX_GRANT_PERCENT = 1);

-- Las tres categorías deben sumar el denominador del hecho ponderado en cada día y escenario.
IF EXISTS (
    SELECT 1
    FROM (
        SELECT p.Escenario, h.KeyTiempo,
               ROUND(SUM(h.ParticipacionesValoradas - h.ParticipacionesPositivas), 0) AS no_positivas
        FROM dbo.HechoSesiones AS h
        JOIN dbo.DimPaciente AS p ON p.KeyPaciente = h.KeyPaciente
        GROUP BY p.Escenario, h.KeyTiempo
    ) AS sesiones
    FULL JOIN dbo.HechoComposicionExperiencia AS c
        ON c.Escenario = sesiones.Escenario AND c.KeyTiempo = sesiones.KeyTiempo
    WHERE COALESCE(sesiones.no_positivas, 0) <> COALESCE(c.ParticipacionesNeutras + c.ParticipacionesNegativas, 0)
)
    THROW 51010, N'El desglose de experiencias y el hecho de sesiones no coinciden.', 1;

COMMIT TRANSACTION;
