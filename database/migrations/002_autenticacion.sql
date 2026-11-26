-- Ejecutar sobre la base transaccional, donde existe dbo.usuario_sistema.
SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.sesion_autenticacion', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.sesion_autenticacion (
        token_hash CHAR(64) NOT NULL PRIMARY KEY,
        id_usuario_sistema BIGINT NOT NULL,
        expira_utc DATETIME2(0) NOT NULL,
        CONSTRAINT FK_sesion_autenticacion_usuario FOREIGN KEY (id_usuario_sistema)
            REFERENCES dbo.usuario_sistema(id_usuario_sistema) ON DELETE CASCADE
    );

    CREATE INDEX IX_sesion_autenticacion_expira
        ON dbo.sesion_autenticacion(expira_utc);
END;

COMMIT TRANSACTION;
