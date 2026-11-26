-- ============================================================================
-- BASE DE DATOS TRANSACCIONAL DE MUSICOTERAPIA - ALZHEIMER (SQL SERVER)
-- Versión rediseñada definitiva: 31 tablas (4 RBAC/Personal + 27 Operativas)
-- Cubre: 7 KPIs, RP01-RP04, FR01-FR08, HIBRIDO vs SINTETICO_IA y 4 Roles
-- ============================================================================
-- NOTA PARA AZURE SQL:
-- En Azure SQL omite este encabezado (USE master / DROP / CREATE DATABASE)
-- y ejecuta directamente desde el BLOQUE 1 sobre tu BD bd_musicoterapia.
-- ============================================================================

USE master;
GO

IF DB_ID('BD_Musicoterapia_Alzheimer') IS NOT NULL
BEGIN
    ALTER DATABASE BD_Musicoterapia_Alzheimer SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE BD_Musicoterapia_Alzheimer;
END
GO

CREATE DATABASE BD_Musicoterapia_Alzheimer;
GO

USE BD_Musicoterapia_Alzheimer;
GO


-- ============================================================================
-- BLOQUE 1: ROLES, PERMISOS Y PERSONAL DEL SISTEMA (Tablas 01 a 04)
-- ============================================================================

-- 01. ROL DEL SISTEMA
CREATE TABLE rol_sistema (
    id_rol_sistema BIGINT IDENTITY(1,1) PRIMARY KEY,
    codigo_rol NVARCHAR(40) NOT NULL UNIQUE,   -- DIRECTOR | CLINICO_EVALUADOR | TERAPEUTA | CUIDADOR_ENFERMERO
    nombre_rol NVARCHAR(100) NOT NULL,
    alcance_datos NVARCHAR(20) NOT NULL,       -- GLOBAL | PROPIOS
    descripcion NVARCHAR(400) NULL,
    CONSTRAINT CHK_rol_alcance CHECK (alcance_datos IN ('GLOBAL', 'PROPIOS'))
);
GO

-- 02. PERMISO (Fichas FR01-FR08, Reportes RP01-RP04 y Administración)
CREATE TABLE permiso (
    id_permiso BIGINT IDENTITY(1,1) PRIMARY KEY,
    codigo_permiso NVARCHAR(60) NOT NULL UNIQUE,
    tipo_recurso NVARCHAR(20) NOT NULL,        -- FICHA | REPORTE | ADMIN
    codigo_recurso NVARCHAR(30) NOT NULL,      -- FR01..FR08 | RP01..RP04 | SISTEMA
    accion NVARCHAR(20) NOT NULL,              -- LEER | ESCRIBIR | GESTIONAR
    descripcion NVARCHAR(300) NULL,
    CONSTRAINT CHK_permiso_tipo CHECK (tipo_recurso IN ('FICHA', 'REPORTE', 'ADMIN')),
    CONSTRAINT CHK_permiso_accion CHECK (accion IN ('LEER', 'ESCRIBIR', 'GESTIONAR'))
);
GO

-- 03. ROL_PERMISO (Matriz de acceso)
CREATE TABLE rol_permiso (
    id_rol_sistema BIGINT NOT NULL,
    id_permiso BIGINT NOT NULL,
    CONSTRAINT PK_rol_permiso PRIMARY KEY (id_rol_sistema, id_permiso),
    CONSTRAINT FK_rolperm_rol FOREIGN KEY (id_rol_sistema) REFERENCES rol_sistema(id_rol_sistema),
    CONSTRAINT FK_rolperm_permiso FOREIGN KEY (id_permiso) REFERENCES permiso(id_permiso)
);
GO

-- 04. USUARIO Y PERSONAL DEL SISTEMA (Unifica cuentas de acceso + personal operativo)
CREATE TABLE usuario_sistema (
    id_usuario_sistema BIGINT IDENTITY(1,1) PRIMARY KEY,
    codigo_personal NVARCHAR(50) NOT NULL UNIQUE, -- Ej: DIR001, EVA001, TER001, ENF001, CUI001
    nombre_completo NVARCHAR(150) NOT NULL,
    cargo_operativo NVARCHAR(60) NOT NULL,        -- DIRECTOR | EVALUADOR_CLINICO | TERAPEUTA | ENFERMERO | CUIDADOR_ASISTENCIAL
    username NVARCHAR(60) NOT NULL UNIQUE,
    email NVARCHAR(150) NOT NULL UNIQUE,
    password_hash NVARCHAR(255) NOT NULL,         -- Hash bcrypt o Argon2 (nunca texto plano)
    id_rol_sistema BIGINT NOT NULL,
    activo BIT NOT NULL DEFAULT 1,
    fecha_creacion DATETIME2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    ultimo_acceso DATETIME2(0) NULL,
    CONSTRAINT FK_usuario_rol FOREIGN KEY (id_rol_sistema) REFERENCES rol_sistema(id_rol_sistema),
    CONSTRAINT CHK_usuario_cargo CHECK (
        cargo_operativo IN ('DIRECTOR', 'EVALUADOR_CLINICO', 'TERAPEUTA', 'ENFERMERO', 'CUIDADOR_ASISTENCIAL')
    )
);
GO


-- ============================================================================
-- BLOQUE 2: PACIENTES, CONTEXTO CLÍNICO Y VISITAS (Tablas 05 a 13)
-- ============================================================================

-- 05. PACIENTE (Seudonimizado: sin nombre ni documento - FR01)
CREATE TABLE paciente (
    id_paciente BIGINT IDENTITY(1,1) PRIMARY KEY,
    codigo_paciente NVARCHAR(60) NOT NULL UNIQUE,
    sexo NVARCHAR(20) NULL,                       -- MASCULINO | FEMENINO | NO_ESPECIFICADO
    fecha_ingreso_programa DATE NOT NULL,
    fecha_salida_programa DATE NULL,
    escenario NVARCHAR(30) NOT NULL DEFAULT 'HIBRIDO', -- HIBRIDO | SINTETICO_IA
    id_usuario_registro BIGINT NULL,
    CONSTRAINT FK_paciente_usuario FOREIGN KEY (id_usuario_registro) REFERENCES usuario_sistema(id_usuario_sistema),
    CONSTRAINT CHK_paciente_escenario CHECK (escenario IN ('HIBRIDO', 'SINTETICO_IA')),
    CONSTRAINT CHK_paciente_fechas CHECK (fecha_salida_programa IS NULL OR fecha_salida_programa >= fecha_ingreso_programa)
);
GO

-- 06. CENTRO DE ATENCION
CREATE TABLE centro_atencion (
    id_centro_atencion BIGINT IDENTITY(1,1) PRIMARY KEY,
    codigo_centro_atencion NVARCHAR(20) NOT NULL UNIQUE,
    nombre_centro_atencion NVARCHAR(200) NOT NULL
);
GO

-- 07. VISITA CLINICA (FR01 clínico / seguimiento longitudinal NACC)
CREATE TABLE visita_clinica (
    id_visita_clinica BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_paciente BIGINT NOT NULL,
    id_centro_atencion BIGINT NULL,
    numero_visita INT NOT NULL,
    fecha_visita DATE NOT NULL,
    edad_paciente_en_visita DECIMAL(5,2) NULL,
    anios_educacion_completados SMALLINT NULL,
    estado_civil NVARCHAR(20) NULL,
    tipo_residencia NVARCHAR(30) NULL,
    id_usuario_registro BIGINT NULL,
    CONSTRAINT FK_visita_paciente FOREIGN KEY (id_paciente) REFERENCES paciente(id_paciente),
    CONSTRAINT FK_visita_centro FOREIGN KEY (id_centro_atencion) REFERENCES centro_atencion(id_centro_atencion),
    CONSTRAINT FK_visita_usuario FOREIGN KEY (id_usuario_registro) REFERENCES usuario_sistema(id_usuario_sistema),
    CONSTRAINT UQ_visita_paciente_numero UNIQUE (id_paciente, numero_visita)
);
GO

-- 08. DIAGNOSTICO PACIENTE
CREATE TABLE diagnostico_paciente (
    id_diagnostico_paciente BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_paciente BIGINT NOT NULL,
    id_visita_clinica BIGINT NULL,
    nombre_diagnostico NVARCHAR(200) NULL,
    estado_cognitivo NVARCHAR(50) NULL,           -- DETERIORO_LEVE | DEMENCIA
    tiene_diagnostico_alzheimer BIT NULL,
    papel_alzheimer_en_diagnostico NVARCHAR(20) NULL, -- PRINCIPAL | CONTRIBUYENTE
    fecha_diagnostico DATE NOT NULL,
    CONSTRAINT FK_diag_paciente FOREIGN KEY (id_paciente) REFERENCES paciente(id_paciente),
    CONSTRAINT FK_diag_visita FOREIGN KEY (id_visita_clinica) REFERENCES visita_clinica(id_visita_clinica)
);
GO

-- 09. SINTOMA VISITA
CREATE TABLE sintoma_visita (
    id_sintoma_visita BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_visita_clinica BIGINT NOT NULL,
    nombre_sintoma NVARCHAR(60) NOT NULL,         -- AGITACION | DEPRESION | ANSIEDAD | APATIA
    presenta_sintoma BIT NULL,
    severidad_sintoma NVARCHAR(20) NULL,          -- LEVE | MODERADA | GRAVE
    CONSTRAINT FK_sintoma_visita FOREIGN KEY (id_visita_clinica) REFERENCES visita_clinica(id_visita_clinica),
    CONSTRAINT UQ_visita_sintoma UNIQUE (id_visita_clinica, nombre_sintoma)
);
GO

-- 10. INSTRUMENTO EVALUACION (MMSE, MOCA, CDR, GDS, CMAI, CSDD)
CREATE TABLE instrumento_evaluacion (
    id_instrumento_evaluacion BIGINT IDENTITY(1,1) PRIMARY KEY,
    codigo_instrumento NVARCHAR(50) NOT NULL UNIQUE,
    nombre_instrumento NVARCHAR(200) NOT NULL,
    tipo_instrumento NVARCHAR(30) NOT NULL,
    unidad_puntuacion NVARCHAR(40) NULL,
    puntuacion_minima_valida DECIMAL(18,6) NULL,
    puntuacion_maxima_valida DECIMAL(18,6) NULL,
    descripcion_escala NVARCHAR(1000) NULL
);
GO

-- 11. MEDICAMENTO
CREATE TABLE medicamento (
    id_medicamento BIGINT IDENTITY(1,1) PRIMARY KEY,
    nombre_medicamento NVARCHAR(250) NOT NULL
);
GO

-- 12. MEDICAMENTO PACIENTE VISITA
CREATE TABLE medicamento_paciente_visita (
    id_medicamento_paciente_visita BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_visita_clinica BIGINT NOT NULL,
    id_medicamento BIGINT NOT NULL,
    CONSTRAINT FK_medvis_visita FOREIGN KEY (id_visita_clinica) REFERENCES visita_clinica(id_visita_clinica),
    CONSTRAINT FK_medvis_medicamento FOREIGN KEY (id_medicamento) REFERENCES medicamento(id_medicamento),
    CONSTRAINT UQ_visita_medicamento UNIQUE (id_visita_clinica, id_medicamento)
);
GO

-- 13. PERFIL GENETICO PACIENTE
CREATE TABLE perfil_genetico_paciente (
    id_perfil_genetico_paciente BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_paciente BIGINT NOT NULL UNIQUE,
    genotipo_apoe NVARCHAR(20) NULL,
    cantidad_alelos_apoe_e4 TINYINT NULL,
    CONSTRAINT FK_genetica_paciente FOREIGN KEY (id_paciente) REFERENCES paciente(id_paciente)
);
GO


-- ============================================================================
-- BLOQUE 3: CATÁLOGO MUSICAL MCUD (Tablas 14 a 22)
-- ============================================================================

-- 14. ARTISTA MUSICAL
CREATE TABLE artista_musical (
    id_artista_musical BIGINT IDENTITY(1,1) PRIMARY KEY,
    nombre_artista NVARCHAR(300) NOT NULL
);
GO

-- 15. CANCION
CREATE TABLE cancion (
    id_cancion BIGINT IDENTITY(1,1) PRIMARY KEY,
    titulo_cancion NVARCHAR(500) NOT NULL,
    nombre_album NVARCHAR(500) NULL,
    tiene_letra BIT NULL,
    anio_publicacion SMALLINT NOT NULL,
    escenario NVARCHAR(30) NOT NULL DEFAULT 'HIBRIDO'
);
GO

-- 16. CANCION ARTISTA
CREATE TABLE cancion_artista (
    id_cancion_artista BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_cancion BIGINT NOT NULL,
    id_artista_musical BIGINT NOT NULL,
    funcion_artista NVARCHAR(30) NULL,
    orden_presentacion_artista SMALLINT NULL,
    CONSTRAINT FK_canart_cancion FOREIGN KEY (id_cancion) REFERENCES cancion(id_cancion),
    CONSTRAINT FK_canart_artista FOREIGN KEY (id_artista_musical) REFERENCES artista_musical(id_artista_musical)
);
GO

-- 17. ETIQUETA MUSICAL
CREATE TABLE etiqueta_musical (
    id_etiqueta_musical BIGINT IDENTITY(1,1) PRIMARY KEY,
    tipo_etiqueta NVARCHAR(20) NOT NULL,
    nombre_etiqueta NVARCHAR(120) NOT NULL,
    CONSTRAINT UQ_etiqueta_tipo_nombre UNIQUE (tipo_etiqueta, nombre_etiqueta)
);
GO

-- 18. CANCION ETIQUETA
CREATE TABLE cancion_etiqueta (
    id_cancion_etiqueta BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_cancion BIGINT NOT NULL,
    id_etiqueta_musical BIGINT NOT NULL,
    CONSTRAINT FK_caneti_cancion FOREIGN KEY (id_cancion) REFERENCES cancion(id_cancion),
    CONSTRAINT FK_caneti_etiqueta FOREIGN KEY (id_etiqueta_musical) REFERENCES etiqueta_musical(id_etiqueta_musical),
    CONSTRAINT UQ_cancion_etiqueta UNIQUE (id_cancion, id_etiqueta_musical)
);
GO

-- 19. CARACTERISTICA MUSICAL
CREATE TABLE caracteristica_musical (
    id_caracteristica_musical BIGINT IDENTITY(1,1) PRIMARY KEY,
    nombre_caracteristica NVARCHAR(200) NOT NULL,
    unidad_caracteristica NVARCHAR(50) NULL,
    tipo_dato_caracteristica NVARCHAR(15) NOT NULL
);
GO

-- 20. VALOR CARACTERISTICA CANCION
CREATE TABLE valor_caracteristica_cancion (
    id_valor_caracteristica_cancion BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_cancion BIGINT NOT NULL,
    id_caracteristica_musical BIGINT NOT NULL,
    valor_numerico FLOAT NULL,
    valor_texto NVARCHAR(MAX) NULL,
    CONSTRAINT FK_valcar_cancion FOREIGN KEY (id_cancion) REFERENCES cancion(id_cancion),
    CONSTRAINT FK_valcar_caracteristica FOREIGN KEY (id_caracteristica_musical) REFERENCES caracteristica_musical(id_caracteristica_musical),
    CONSTRAINT UQ_cancion_caracteristica UNIQUE (id_cancion, id_caracteristica_musical)
);
GO

-- 21. LISTA REPRODUCCION
CREATE TABLE lista_reproduccion (
    id_lista_reproduccion BIGINT IDENTITY(1,1) PRIMARY KEY,
    nombre_lista_reproduccion NVARCHAR(200) NOT NULL,
    objetivo_intervencion NVARCHAR(300) NULL,
    indicaciones_uso NVARCHAR(300) NULL
);
GO

-- 22. LISTA REPRODUCCION CANCION
CREATE TABLE lista_reproduccion_cancion (
    id_lista_reproduccion_cancion BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_lista_reproduccion BIGINT NOT NULL,
    orden_cancion_en_lista SMALLINT NOT NULL,
    id_cancion BIGINT NOT NULL,
    CONSTRAINT FK_listacan_lista FOREIGN KEY (id_lista_reproduccion) REFERENCES lista_reproduccion(id_lista_reproduccion),
    CONSTRAINT FK_listacan_cancion FOREIGN KEY (id_cancion) REFERENCES cancion(id_cancion),
    CONSTRAINT UQ_lista_orden UNIQUE (id_lista_reproduccion, orden_cancion_en_lista)
);
GO


-- ============================================================================
-- BLOQUE 4: INTERVENCIÓN MUSICAL, EVALUACIONES Y AGITACIÓN (Tablas 23 a 31)
-- ============================================================================

-- 23. SESION MUSICAL (FR02 y FR03)
CREATE TABLE sesion_musical (
    id_sesion_musical BIGINT IDENTITY(1,1) PRIMARY KEY,
    codigo_sesion NVARCHAR(100) NOT NULL UNIQUE,
    modalidad_sesion NVARCHAR(30) NOT NULL,                 -- INDIVIDUAL | GRUPAL
    tipo_actividad NVARCHAR(40) NOT NULL DEFAULT 'ESCUCHA', -- ESCUCHA | CANTO | ESTIMULACION_SENSORIAL | OTRA
    fecha_hora_inicio_sesion DATETIME2(0) NOT NULL,
    fecha_hora_inicio_musica DATETIME2(0) NULL,             -- Punto de partida exacto para KPI 6 (FR03)
    fecha_hora_fin_sesion DATETIME2(0) NOT NULL,
    id_lista_reproduccion BIGINT NULL,
    id_responsable BIGINT NOT NULL,                         -- Terapeuta o Cuidador responsable (FK usuario_sistema)
    CONSTRAINT FK_sesion_lista FOREIGN KEY (id_lista_reproduccion) REFERENCES lista_reproduccion(id_lista_reproduccion),
    CONSTRAINT FK_sesion_responsable FOREIGN KEY (id_responsable) REFERENCES usuario_sistema(id_usuario_sistema),
    CONSTRAINT CHK_sesion_modalidad CHECK (modalidad_sesion IN ('INDIVIDUAL', 'GRUPAL')),
    CONSTRAINT CHK_sesion_horas CHECK (fecha_hora_fin_sesion >= fecha_hora_inicio_sesion),
    CONSTRAINT CHK_sesion_inicio_musica CHECK (
        fecha_hora_inicio_musica IS NULL
        OR (fecha_hora_inicio_musica >= fecha_hora_inicio_sesion AND fecha_hora_inicio_musica <= fecha_hora_fin_sesion)
    )
);
GO

-- 24. PARTICIPACION SESION (FR03 y fuente directa para KPI 1, KPI 4 y KPI 6)
CREATE TABLE participacion_sesion (
    id_participacion_sesion BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_sesion_musical BIGINT NOT NULL,
    id_paciente BIGINT NOT NULL,
    fecha_hora_ingreso_paciente DATETIME2(0) NULL,
    fecha_hora_salida_paciente DATETIME2(0) NULL,
    estado_participacion NVARCHAR(30) NOT NULL DEFAULT 'COMPLETA', -- COMPLETA | INTERRUMPIDA | AUSENTE
    motivo_interrupcion NVARCHAR(500) NULL,
    experiencia_sesion NVARCHAR(20) NULL,            -- POSITIVA | NEUTRA | NEGATIVA | NO_SABE
    efecto_resto_dia NVARCHAR(20) NULL,              -- POSITIVO | NEUTRO | NEGATIVO | NO_SABE
    estado_respuesta_positiva NVARCHAR(30) NULL,     -- OBSERVADA | SIN_RESPUESTA | NO_OBSERVADA
    fecha_hora_primera_respuesta DATETIME2(0) NULL,  -- Hora exacta de 1ra respuesta positiva (FR03)
    minutos_hasta_primera_respuesta DECIMAL(6,2) NULL, -- Latencia en minutos desde inicio_musica (0=inmediata, NULL=sin respuesta)
    puntaje_agitacion_antes TINYINT NULL,            -- Escala breve FR03 (0 a 16)
    puntaje_agitacion_despues TINYINT NULL,          -- Escala breve FR03 (0 a 16)
    comentarios NVARCHAR(500) NULL,
    CONSTRAINT FK_part_sesion FOREIGN KEY (id_sesion_musical) REFERENCES sesion_musical(id_sesion_musical),
    CONSTRAINT FK_part_paciente FOREIGN KEY (id_paciente) REFERENCES paciente(id_paciente),
    CONSTRAINT UQ_sesion_paciente UNIQUE (id_sesion_musical, id_paciente),
    CONSTRAINT CHK_part_estado CHECK (estado_participacion IN ('COMPLETA', 'INTERRUMPIDA', 'AUSENTE')),
    CONSTRAINT CHK_part_exp CHECK (experiencia_sesion IS NULL OR experiencia_sesion IN ('POSITIVA', 'NEUTRA', 'NEGATIVA', 'NO_SABE')),
    CONSTRAINT CHK_part_efecto CHECK (efecto_resto_dia IS NULL OR efecto_resto_dia IN ('POSITIVO', 'NEUTRO', 'NEGATIVO', 'NO_SABE')),
    CONSTRAINT CHK_part_resp CHECK (estado_respuesta_positiva IS NULL OR estado_respuesta_positiva IN ('OBSERVADA', 'SIN_RESPUESTA', 'NO_OBSERVADA')),
    CONSTRAINT CHK_part_latencia CHECK (minutos_hasta_primera_respuesta IS NULL OR minutos_hasta_primera_respuesta >= 0),
    CONSTRAINT CHK_part_agit_antes CHECK (puntaje_agitacion_antes IS NULL OR (puntaje_agitacion_antes BETWEEN 0 AND 16)),
    CONSTRAINT CHK_part_agit_desp CHECK (puntaje_agitacion_despues IS NULL OR (puntaje_agitacion_despues BETWEEN 0 AND 16))
);
GO

-- 25. EXPOSICION MUSICAL (FR02: múltiples pistas secuenciales por participación)
CREATE TABLE exposicion_musical (
    id_exposicion_musical BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_participacion_sesion BIGINT NOT NULL,
    id_cancion BIGINT NOT NULL,
    orden_reproduccion SMALLINT NOT NULL,
    fecha_hora_inicio_cancion DATETIME2(0) NOT NULL,
    fecha_hora_fin_cancion DATETIME2(0) NOT NULL,
    CONSTRAINT FK_expo_participacion FOREIGN KEY (id_participacion_sesion) REFERENCES participacion_sesion(id_participacion_sesion),
    CONSTRAINT FK_expo_cancion FOREIGN KEY (id_cancion) REFERENCES cancion(id_cancion),
    CONSTRAINT CHK_expo_horas CHECK (fecha_hora_fin_cancion >= fecha_hora_inicio_cancion)
);
GO

-- 26. OBSERVACION PACIENTE (FR03 observación complementaria vinculada a la canción)
CREATE TABLE observacion_paciente (
    id_observacion_paciente BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_participacion_sesion BIGINT NOT NULL,
    id_exposicion_musical BIGINT NULL,
    id_observador BIGINT NULL,                       -- Personal que registró la observación (FK usuario_sistema)
    fecha_hora_observacion DATETIME2(0) NOT NULL,
    descripcion_observacion NVARCHAR(1000) NOT NULL,
    tipo_observacion NVARCHAR(30) NOT NULL,
    CONSTRAINT FK_obs_participacion FOREIGN KEY (id_participacion_sesion) REFERENCES participacion_sesion(id_participacion_sesion),
    CONSTRAINT FK_obs_exposicion FOREIGN KEY (id_exposicion_musical) REFERENCES exposicion_musical(id_exposicion_musical),
    CONSTRAINT FK_obs_observador FOREIGN KEY (id_observador) REFERENCES usuario_sistema(id_usuario_sistema)
);
GO

-- 27. CLASIFICACION OBSERVACION
CREATE TABLE clasificacion_observacion (
    id_clasificacion_observacion BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_observacion_paciente BIGINT NOT NULL,
    nombre_respuesta_observada NVARCHAR(40) NOT NULL, -- SONRISA | CANTO | MOVIMIENTO | CALMA | ALEGRIA | PARTICIPACION
    descripcion_conducta_clasificada NVARCHAR(500) NULL,
    CONSTRAINT FK_clasobs_observacion FOREIGN KEY (id_observacion_paciente) REFERENCES observacion_paciente(id_observacion_paciente)
);
GO

-- 28. EVALUACION PACIENTE (FR05 CMAI, FR06 CSDD, FR07 MMSE + Visitas NACC)
CREATE TABLE evaluacion_paciente (
    id_evaluacion_paciente BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_paciente BIGINT NOT NULL,
    id_visita_clinica BIGINT NULL,
    id_participacion_sesion BIGINT NULL,
    id_exposicion_musical BIGINT NULL,
    id_evaluador BIGINT NULL,                        -- Evaluador clínico responsable (FK usuario_sistema)
    momento_evaluacion NVARCHAR(30) NOT NULL,        -- INICIAL | SEGUIMIENTO
    condicion_evaluada NVARCHAR(40) NOT NULL,        -- CLINICA | INTERVENCION
    nivel_evaluacion NVARCHAR(30) NOT NULL,          -- VISITA | SESION
    fecha_hora_evaluacion DATETIME2(0) NOT NULL,
    ventana_inicio_fecha DATE NULL,                  -- Ventana de 1 semana para CMAI (FR05)
    ventana_fin_fecha DATE NULL,
    CONSTRAINT FK_eval_paciente FOREIGN KEY (id_paciente) REFERENCES paciente(id_paciente),
    CONSTRAINT FK_eval_visita FOREIGN KEY (id_visita_clinica) REFERENCES visita_clinica(id_visita_clinica),
    CONSTRAINT FK_eval_participacion FOREIGN KEY (id_participacion_sesion) REFERENCES participacion_sesion(id_participacion_sesion),
    CONSTRAINT FK_eval_exposicion FOREIGN KEY (id_exposicion_musical) REFERENCES exposicion_musical(id_exposicion_musical),
    CONSTRAINT FK_eval_evaluador FOREIGN KEY (id_evaluador) REFERENCES usuario_sistema(id_usuario_sistema),
    CONSTRAINT CHK_eval_momento CHECK (momento_evaluacion IN ('INICIAL', 'SEGUIMIENTO'))
);
GO

-- 29. RESULTADO EVALUACION (KPI 2, KPI 3 y KPI 5)
CREATE TABLE resultado_evaluacion (
    id_resultado_evaluacion BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_evaluacion_paciente BIGINT NOT NULL,
    id_instrumento_evaluacion BIGINT NOT NULL,
    puntuacion_obtenida DECIMAL(18,6) NULL,
    estado_puntaje NVARCHAR(20) NOT NULL DEFAULT 'VALIDO', -- VALIDO | NO_EVALUABLE | NO_CONSTA (FR05-FR07)
    motivo_sin_puntuacion NVARCHAR(100) NULL,
    forma_calculo_puntuacion NVARCHAR(100) NULL,
    CONSTRAINT FK_reseval_evaluacion FOREIGN KEY (id_evaluacion_paciente) REFERENCES evaluacion_paciente(id_evaluacion_paciente),
    CONSTRAINT FK_reseval_instrumento FOREIGN KEY (id_instrumento_evaluacion) REFERENCES instrumento_evaluacion(id_instrumento_evaluacion),
    CONSTRAINT CHK_reseval_estado CHECK (estado_puntaje IN ('VALIDO', 'NO_EVALUABLE', 'NO_CONSTA'))
);
GO

-- 30. AGITACION POR TURNO (KPI 7 - FR08)
CREATE TABLE agitacion_turno (
    id_agitacion_turno BIGINT IDENTITY(1,1) PRIMARY KEY,
    id_paciente BIGINT NOT NULL,
    id_responsable BIGINT NOT NULL,                  -- Cuidador / Enfermero del turno (FK usuario_sistema)
    fecha_turno DATE NOT NULL,
    tipo_turno NVARCHAR(20) NOT NULL,                -- MANANA | TARDE | NOCHE
    hora_inicio_turno TIME(0) NULL,
    hora_fin_turno TIME(0) NULL,
    cobertura_observacion NVARCHAR(30) NOT NULL,     -- OBSERVADO | OBSERVACION_PARCIAL | NO_OBSERVADO
    total_episodios INT NULL,                        -- 0 si observado sin episodios; NULL si NO_OBSERVADO
    observaciones NVARCHAR(500) NULL,
    CONSTRAINT FK_agiturno_paciente FOREIGN KEY (id_paciente) REFERENCES paciente(id_paciente),
    CONSTRAINT FK_agiturno_responsable FOREIGN KEY (id_responsable) REFERENCES usuario_sistema(id_usuario_sistema),
    CONSTRAINT UQ_agiturno_paciente_fecha_turno UNIQUE (id_paciente, fecha_turno, tipo_turno),
    CONSTRAINT CHK_agiturno_tipo CHECK (tipo_turno IN ('MANANA', 'TARDE', 'NOCHE')),
    CONSTRAINT CHK_agiturno_cobertura CHECK (cobertura_observacion IN ('OBSERVADO', 'OBSERVACION_PARCIAL', 'NO_OBSERVADO')),
    CONSTRAINT CHK_agiturno_episodios CHECK (total_episodios IS NULL OR total_episodios >= 0)
);
GO

-- 31. CONTROL SEMANAL DE INTERVENCION (FR04 y denominador de KPI 4)
-- Los totales de sesiones y minutos se calculan desde participacion_sesion.
-- Sin una ficha confirmada no se infiere que un paciente estuvo en intervencion.
CREATE TABLE control_semanal_intervencion (
    id_control_semanal BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
    id_paciente BIGINT NOT NULL,
    fecha_inicio_semana DATE NOT NULL,
    codigo_programa NVARCHAR(50) NOT NULL DEFAULT N'MUSICOTERAPIA',
    en_intervencion BIT NOT NULL,
    cobertura_registro NVARCHAR(20) NULL, -- COMPLETA | INSUFICIENTE | CERO_CONFIRMADO
    codigo_responsable NVARCHAR(50) NOT NULL,
    observaciones NVARCHAR(500) NULL,
    fecha_actualizacion_utc DATETIME2(0) NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT FK_fr04_paciente FOREIGN KEY (id_paciente) REFERENCES paciente(id_paciente),
    CONSTRAINT FK_fr04_responsable FOREIGN KEY (codigo_responsable) REFERENCES usuario_sistema(codigo_personal),
    CONSTRAINT UQ_fr04_paciente_semana_programa UNIQUE (id_paciente, fecha_inicio_semana, codigo_programa),
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
GO


-- ============================================================================
-- BLOQUE 5: ÍNDICES ESTRATÉGICOS PARA CONSULTAS Y ETL HACIA DATA MART
-- ============================================================================

CREATE INDEX IX_paciente_escenario ON paciente(escenario) INCLUDE (fecha_ingreso_programa, fecha_salida_programa, sexo);
CREATE INDEX IX_visita_paciente_fecha ON visita_clinica(id_paciente, fecha_visita);
CREATE INDEX IX_sesion_fecha_resp ON sesion_musical(fecha_hora_inicio_sesion, id_responsable) INCLUDE (modalidad_sesion, tipo_actividad, id_lista_reproduccion);
CREATE INDEX IX_part_paciente_sesion ON participacion_sesion(id_paciente, id_sesion_musical) INCLUDE (estado_participacion, experiencia_sesion, estado_respuesta_positiva, minutos_hasta_primera_respuesta);
CREATE INDEX IX_expo_participacion ON exposicion_musical(id_participacion_sesion) INCLUDE (id_cancion, orden_reproduccion);
CREATE INDEX IX_eval_paciente_fecha ON evaluacion_paciente(id_paciente, fecha_hora_evaluacion) INCLUDE (momento_evaluacion, condicion_evaluada, id_evaluador);
CREATE INDEX IX_reseval_inst_eval ON resultado_evaluacion(id_instrumento_evaluacion, id_evaluacion_paciente) INCLUDE (puntuacion_obtenida, estado_puntaje);
CREATE INDEX IX_agiturno_paciente_fecha ON agitacion_turno(id_paciente, fecha_turno) INCLUDE (tipo_turno, cobertura_observacion, total_episodios, id_responsable);
CREATE INDEX IX_fr04_semana_programa ON control_semanal_intervencion(fecha_inicio_semana, codigo_programa, en_intervencion) INCLUDE (cobertura_registro);
GO


-- ============================================================================
-- BLOQUE 6: CARGA INICIAL DE ROLES Y MATRIZ DE PERMISOS (Según Capítulo IV)
-- ============================================================================
-- NOTA: Si vas a migrar datos con BCP hacia Azure SQL, NO ejecutes el BLOQUE 6
-- en Azure (bcp subirá estos mismos registros respetando sus IDs originales).
-- ============================================================================

INSERT INTO rol_sistema (codigo_rol, nombre_rol, alcance_datos, descripcion) VALUES
('DIRECTOR',           'Director / Gestor del Centro', 'GLOBAL',  'Acceso total a RP01-RP04, alta anonimizada FR01, escenarios y gestión de usuarios/roles.'),
('CLINICO_EVALUADOR',  'Personal Clínico / Evaluador', 'GLOBAL',  'Registro clínico FR01 y escalas FR05-FR07; consulta RP02, RP04 y lectura de RP01/RP03.'),
('TERAPEUTA',          'Terapeuta Musical',            'GLOBAL',  'Registro de preferencias FR01, música FR02, diario FR03 y control FR04; consulta RP01 y RP03.'),
('CUIDADOR_ENFERMERO', 'Cuidador / Enfermero',         'PROPIOS', 'Registro de diario FR03 y turnos FR08; consulta RP01 y RP04 filtrado a sus propios registros.');
GO

INSERT INTO permiso (codigo_permiso, tipo_recurso, codigo_recurso, accion, descripcion) VALUES
-- Administración y escenarios
('GESTIONAR_USUARIOS',  'ADMIN',   'SISTEMA', 'GESTIONAR', 'Crear, editar y asignar roles a cuentas de usuario'),
('VER_ESCENARIOS',      'REPORTE', 'SISTEMA', 'LEER',      'Comparar escenarios HIBRIDO vs SINTETICO_IA'),
-- Fichas de recolección (Escritura)
('REGISTRAR_FR01_ALTA', 'FICHA',   'FR01',    'ESCRIBIR',  'Alta del código anonimizado del paciente'),
('REGISTRAR_FR01_CLIN', 'FICHA',   'FR01',    'ESCRIBIR',  'Registrar diagnóstico, etapa y medicación'),
('REGISTRAR_FR01_PREF', 'FICHA',   'FR01',    'ESCRIBIR',  'Registrar historia y preferencias musicales'),
('REGISTRAR_FR02',      'FICHA',   'FR02',    'ESCRIBIR',  'Registrar música y playlists utilizadas en sesión'),
('REGISTRAR_FR03',      'FICHA',   'FR03',    'ESCRIBIR',  'Registrar diario de sesión y observación complementaria'),
('REGISTRAR_FR04',      'FICHA',   'FR04',    'ESCRIBIR',  'Registrar control semanal de adherencia'),
('REGISTRAR_FR05',      'FICHA',   'FR05',    'ESCRIBIR',  'Transcribir evaluación de agitación CMAI'),
('REGISTRAR_FR06',      'FICHA',   'FR06',    'ESCRIBIR',  'Transcribir evaluación de depresión CSDD'),
('REGISTRAR_FR07',      'FICHA',   'FR07',    'ESCRIBIR',  'Transcribir evaluación cognitiva MMSE'),
('REGISTRAR_FR08',      'FICHA',   'FR08',    'ESCRIBIR',  'Registrar episodios de agitación por turno'),
-- Reportes BI (Lectura)
('VER_RP01',            'REPORTE', 'RP01',    'LEER',      'Consultar RP01: Respuesta por sesión (K1 y K6)'),
('VER_RP02',            'REPORTE', 'RP02',    'LEER',      'Consultar RP02: Evolución de evaluaciones (K2, K3 y K5)'),
('VER_RP03',            'REPORTE', 'RP03',    'LEER',      'Consultar RP03: Seguimiento de adherencia (K4)'),
('VER_RP04',            'REPORTE', 'RP04',    'LEER',      'Consultar RP04: Agitación por turno (K7)');
GO

INSERT INTO rol_permiso (id_rol_sistema, id_permiso)
SELECT r.id_rol_sistema, p.id_permiso
FROM rol_sistema r
INNER JOIN permiso p ON
    (r.codigo_rol = 'DIRECTOR' AND p.codigo_permiso IN (
        'GESTIONAR_USUARIOS', 'VER_ESCENARIOS', 'REGISTRAR_FR01_ALTA',
        'VER_RP01', 'VER_RP02', 'VER_RP03', 'VER_RP04'
    ))
    OR
    (r.codigo_rol = 'CLINICO_EVALUADOR' AND p.codigo_permiso IN (
        'REGISTRAR_FR01_CLIN', 'REGISTRAR_FR05', 'REGISTRAR_FR06', 'REGISTRAR_FR07',
        'VER_RP01', 'VER_RP02', 'VER_RP03', 'VER_RP04'
    ))
    OR
    (r.codigo_rol = 'TERAPEUTA' AND p.codigo_permiso IN (
        'REGISTRAR_FR01_PREF', 'REGISTRAR_FR02', 'REGISTRAR_FR03', 'REGISTRAR_FR04',
        'VER_RP01', 'VER_RP03'
    ))
    OR
    (r.codigo_rol = 'CUIDADOR_ENFERMERO' AND p.codigo_permiso IN (
        'REGISTRAR_FR03', 'REGISTRAR_FR08',
        'VER_RP01', 'VER_RP04'
    ));
GO
