-- Conserva las visitas, diagnósticos y sesiones históricas.
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF COL_LENGTH(N'dbo.diagnostico_paciente', N'codigo_cie10') IS NULL
        ALTER TABLE dbo.diagnostico_paciente ADD codigo_cie10 NVARCHAR(16) NULL;

    IF COL_LENGTH(N'dbo.diagnostico_paciente', N'etapa_alzheimer') IS NULL
        ALTER TABLE dbo.diagnostico_paciente ADD etapa_alzheimer NVARCHAR(15) NULL
            CONSTRAINT CHK_diagnostico_etapa_alzheimer
            CHECK (etapa_alzheimer IN (N'LEVE', N'MODERADA', N'OTRA', N'NO_CONSTA'));

    IF COL_LENGTH(N'dbo.visita_clinica', N'antecedentes_fr01') IS NULL
        ALTER TABLE dbo.visita_clinica ADD antecedentes_fr01 NVARCHAR(500) NULL,
            tabaquismo_fr01 NVARCHAR(100) NULL, gold_msi_fr01 DECIMAL(7,2) NULL,
            antipsicoticos_fr01 BIT NULL, antidepresivos_fr01 BIT NULL, ansioliticos_fr01 BIT NULL;

    IF OBJECT_ID(N'dbo.preferencia_musical_paciente', N'U') IS NULL
        CREATE TABLE dbo.preferencia_musical_paciente (
            id_paciente BIGINT NOT NULL PRIMARY KEY REFERENCES dbo.paciente(id_paciente),
            fuente NVARCHAR(20) NOT NULL CHECK (fuente IN (N'PACIENTE', N'FAMILIAR', N'CUIDADOR', N'OTRA')),
            antecedentes NVARCHAR(500) NULL,
            preferencias NVARCHAR(500) NULL,
            musica_a_evitar NVARCHAR(500) NULL,
            observaciones NVARCHAR(500) NULL,
            id_usuario_registro BIGINT NOT NULL REFERENCES dbo.usuario_sistema(id_usuario_sistema),
            fecha_actualizacion_utc DATETIME2(0) NOT NULL DEFAULT SYSUTCDATETIME()
        );

    IF COL_LENGTH(N'dbo.sesion_musical', N'uso_musica') IS NULL
        ALTER TABLE dbo.sesion_musical ADD uso_musica NVARCHAR(20) NULL
            CONSTRAINT CHK_sesion_uso_musica CHECK (uso_musica IN (N'SIN_MUSICA', N'SIN_DETALLE', N'PISTAS', N'LISTA'));

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
