-- FR04: vigencia y cobertura por paciente y semana ISO.
-- No rellena retrospectivamente la tabla: la pertenencia a la intervencion
-- y la ausencia confirmada de sesiones requieren evidencia.
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID(N'dbo.control_semanal_intervencion', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.control_semanal_intervencion (
            id_control_semanal BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            id_paciente BIGINT NOT NULL,
            fecha_inicio_semana DATE NOT NULL,
            codigo_programa NVARCHAR(50) NOT NULL DEFAULT N'MUSICOTERAPIA',
            en_intervencion BIT NOT NULL,
            cobertura_registro NVARCHAR(20) NULL,
            codigo_responsable NVARCHAR(50) NOT NULL,
            observaciones NVARCHAR(500) NULL,
            fecha_actualizacion_utc DATETIME2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
            CONSTRAINT FK_fr04_paciente FOREIGN KEY (id_paciente)
                REFERENCES dbo.paciente(id_paciente),
            CONSTRAINT UQ_fr04_paciente_semana_programa
                UNIQUE (id_paciente, fecha_inicio_semana, codigo_programa),
            CONSTRAINT CHK_fr04_lunes CHECK (
                DATEDIFF(day, CONVERT(date, '19000101', 112), fecha_inicio_semana) % 7 = 0
            ),
            CONSTRAINT CHK_fr04_cobertura CHECK (
                (en_intervencion = 0 AND cobertura_registro IS NULL)
                OR (en_intervencion = 1 AND cobertura_registro IN
                    (N'COMPLETA', N'INSUFICIENTE', N'CERO_CONFIRMADO'))
            ),
            CONSTRAINT CHK_fr04_responsable CHECK (LEN(LTRIM(RTRIM(codigo_responsable))) > 0)
        );
    END;

    IF NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys
        WHERE parent_object_id = OBJECT_ID(N'dbo.control_semanal_intervencion')
          AND name = N'FK_fr04_responsable'
    )
    BEGIN
        ALTER TABLE dbo.control_semanal_intervencion WITH CHECK
        ADD CONSTRAINT FK_fr04_responsable FOREIGN KEY (codigo_responsable)
            REFERENCES dbo.usuario_sistema(codigo_personal);
    END;

    IF NOT EXISTS (
        SELECT 1 FROM sys.indexes
        WHERE object_id = OBJECT_ID(N'dbo.control_semanal_intervencion')
          AND name = N'IX_fr04_semana_programa'
    )
    BEGIN
        CREATE INDEX IX_fr04_semana_programa
            ON dbo.control_semanal_intervencion(fecha_inicio_semana, codigo_programa, en_intervencion)
            INCLUDE (cobertura_registro);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
