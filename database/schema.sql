create table dbo.artista_musical
(
    id_artista_musical bigint identity
        primary key,
    nombre_artista     nvarchar(300) not null
);

create table dbo.cancion
(
    id_cancion       bigint identity
        primary key,
    titulo_cancion   nvarchar(500)                  not null,
    nombre_album     nvarchar(500),
    tiene_letra      bit,
    anio_publicacion smallint                       not null,
    escenario        nvarchar(30) default 'HIBRIDO' not null
);

create table dbo.cancion_artista
(
    id_cancion_artista         bigint identity
        primary key,
    id_cancion                 bigint not null
        constraint FK_canart_cancion
            references dbo.cancion,
    id_artista_musical         bigint not null
        constraint FK_canart_artista
            references dbo.artista_musical,
    funcion_artista            nvarchar(30),
    orden_presentacion_artista smallint
);

create table dbo.caracteristica_musical
(
    id_caracteristica_musical bigint identity
        primary key,
    nombre_caracteristica     nvarchar(200) not null,
    unidad_caracteristica     nvarchar(50),
    tipo_dato_caracteristica  nvarchar(15)  not null
);

create table dbo.centro_atencion
(
    id_centro_atencion     bigint identity
        primary key,
    codigo_centro_atencion nvarchar(20)  not null
        unique,
    nombre_centro_atencion nvarchar(200) not null
);

create table dbo.cuidador
(
    id_cuidador     bigint identity
        primary key,
    codigo_cuidador nvarchar(50)  not null
        unique,
    rol_cuidador    nvarchar(40)  not null,
    nombre_cuidador nvarchar(150) not null
);

create table dbo.etiqueta_musical
(
    id_etiqueta_musical bigint identity
        primary key,
    tipo_etiqueta       nvarchar(20)  not null,
    nombre_etiqueta     nvarchar(120) not null,
    constraint UQ_etiqueta_tipo_nombre
        unique (tipo_etiqueta, nombre_etiqueta)
);

create table dbo.cancion_etiqueta
(
    id_cancion_etiqueta bigint identity
        primary key,
    id_cancion          bigint not null
        constraint FK_caneti_cancion
            references dbo.cancion,
    id_etiqueta_musical bigint not null
        constraint FK_caneti_etiqueta
            references dbo.etiqueta_musical,
    constraint UQ_cancion_etiqueta
        unique (id_cancion, id_etiqueta_musical)
);

create table dbo.instrumento_evaluacion
(
    id_instrumento_evaluacion bigint identity
        primary key,
    codigo_instrumento        nvarchar(50)  not null
        unique,
    nombre_instrumento        nvarchar(200) not null,
    tipo_instrumento          nvarchar(30)  not null,
    unidad_puntuacion         nvarchar(40),
    puntuacion_minima_valida  decimal(18, 6),
    puntuacion_maxima_valida  decimal(18, 6),
    descripcion_escala        nvarchar(1000)
);

create table dbo.lista_reproduccion
(
    id_lista_reproduccion     bigint identity
        primary key,
    nombre_lista_reproduccion nvarchar(200) not null,
    objetivo_intervencion     nvarchar(300),
    indicaciones_uso          nvarchar(300)
);

create table dbo.lista_reproduccion_cancion
(
    id_lista_reproduccion_cancion bigint identity
        primary key,
    id_lista_reproduccion         bigint   not null
        constraint FK_listacan_lista
            references dbo.lista_reproduccion,
    orden_cancion_en_lista        smallint not null,
    id_cancion                    bigint   not null
        constraint FK_listacan_cancion
            references dbo.cancion,
    constraint UQ_lista_orden
        unique (id_lista_reproduccion, orden_cancion_en_lista)
);

create table dbo.medicamento
(
    id_medicamento     bigint identity
        primary key,
    nombre_medicamento nvarchar(250) not null
);

create table dbo.paciente
(
    id_paciente            bigint identity
        primary key,
    codigo_paciente        nvarchar(60)                   not null
        unique,
    sexo                   nvarchar(20),
    estado_seguimiento     nvarchar(30),
    fecha_ingreso_programa date,
    fecha_salida_programa  date,
    escenario              nvarchar(30) default 'HIBRIDO' not null
);

create table dbo.agitacion_turno
(
    id_agitacion_turno      bigint identity
        primary key,
    id_paciente             bigint       not null
        constraint FK_agiturno_paciente
            references dbo.paciente,
    id_cuidador_responsable bigint
        constraint FK_agiturno_cuidador
            references dbo.cuidador,
    fecha_turno             date         not null,
    tipo_turno              nvarchar(20) not null,
    hora_inicio_turno       time,
    hora_fin_turno          time,
    cobertura_observacion   nvarchar(30) not null,
    total_episodios         int,
    observaciones           nvarchar(1000),
    constraint UQ_agiturno_paciente_fecha_turno
        unique (id_paciente, fecha_turno, tipo_turno)
);

create table dbo.perfil_genetico_paciente
(
    id_perfil_genetico_paciente bigint identity
        primary key,
    id_paciente                 bigint not null
        unique
        constraint FK_genetica_paciente
            references dbo.paciente,
    genotipo_apoe               nvarchar(20),
    cantidad_alelos_apoe_e4     tinyint
);

create table dbo.sesion_musical
(
    id_sesion_musical        bigint identity
        primary key,
    codigo_sesion            nvarchar(100)                  not null
        unique,
    modalidad_sesion         nvarchar(30)                   not null,
    tipo_actividad           nvarchar(40) default 'ESCUCHA' not null,
    fecha_hora_inicio_sesion datetime2(6)                   not null,
    fecha_hora_fin_sesion    datetime2(6)                   not null,
    id_lista_reproduccion    bigint
        constraint FK_sesion_lista
            references dbo.lista_reproduccion,
    id_cuidador_responsable  bigint
        constraint FK_sesion_cuidador
            references dbo.cuidador,
    constraint CHK_sesion_horas
        check ([fecha_hora_fin_sesion] >= [fecha_hora_inicio_sesion])
);

create table dbo.participacion_sesion
(
    id_participacion_sesion     bigint identity
        primary key,
    id_sesion_musical           bigint not null
        constraint FK_part_sesion
            references dbo.sesion_musical,
    id_paciente                 bigint not null
        constraint FK_part_paciente
            references dbo.paciente,
    fecha_hora_ingreso_paciente datetime2(6),
    fecha_hora_salida_paciente  datetime2(6),
    estado_participacion        nvarchar(30),
    motivo_interrupcion         nvarchar(1000),
    experiencia_sesion          nvarchar(20),
    efecto_resto_dia            nvarchar(20),
    estado_respuesta_positiva   nvarchar(30),
    constraint UQ_sesion_paciente
        unique (id_sesion_musical, id_paciente)
);

create table dbo.exposicion_musical
(
    id_exposicion_musical     bigint identity
        primary key,
    id_participacion_sesion   bigint       not null
        constraint FK_expo_participacion
            references dbo.participacion_sesion,
    id_cancion                bigint       not null
        constraint FK_expo_cancion
            references dbo.cancion,
    orden_reproduccion        smallint,
    fecha_hora_inicio_cancion datetime2(6) not null,
    fecha_hora_fin_cancion    datetime2(6) not null,
    constraint CHK_expo_horas
        check ([fecha_hora_fin_cancion] >= [fecha_hora_inicio_cancion])
);

create table dbo.observacion_paciente
(
    id_observacion_paciente bigint identity
        primary key,
    id_participacion_sesion bigint        not null
        constraint FK_obs_participacion
            references dbo.participacion_sesion,
    id_exposicion_musical   bigint
        constraint FK_obs_exposicion
            references dbo.exposicion_musical,
    id_cuidador_observador  bigint
        constraint FK_obs_cuidador
            references dbo.cuidador,
    fecha_hora_observacion  datetime2(6)  not null,
    descripcion_observacion nvarchar(max) not null,
    tipo_observacion        nvarchar(30)  not null
);

create table dbo.clasificacion_observacion
(
    id_clasificacion_observacion     bigint identity
        primary key,
    id_observacion_paciente          bigint       not null
        constraint FK_clasobs_observacion
            references dbo.observacion_paciente,
    nombre_respuesta_observada       nvarchar(40) not null,
    descripcion_conducta_clasificada nvarchar(1000)
);

create table dbo.sysdiagrams
(
    name         sysname not null,
    principal_id int     not null,
    diagram_id   int identity
        primary key,
    version      int,
    definition   varbinary(max),
    constraint UK_principal_name
        unique (principal_id, name)
);

exec sp_addextendedproperty 'microsoft_database_tools_support', 1, 'SCHEMA', 'dbo', 'TABLE', 'sysdiagrams';

create table dbo.valor_caracteristica_cancion
(
    id_valor_caracteristica_cancion bigint identity
        primary key,
    id_cancion                      bigint not null
        constraint FK_valcar_cancion
            references dbo.cancion,
    id_caracteristica_musical       bigint not null
        constraint FK_valcar_caracteristica
            references dbo.caracteristica_musical,
    valor_numerico                  float,
    valor_texto                     nvarchar(max),
    constraint UQ_cancion_caracteristica
        unique (id_cancion, id_caracteristica_musical)
);

create table dbo.visita_clinica
(
    id_visita_clinica           bigint identity
        primary key,
    id_paciente                 bigint not null
        constraint FK_visita_paciente
            references dbo.paciente,
    id_centro_atencion          bigint
        constraint FK_visita_centro
            references dbo.centro_atencion,
    numero_visita               int    not null,
    fecha_visita                date   not null,
    edad_paciente_en_visita     decimal(5, 2),
    anios_educacion_completados smallint,
    estado_civil                nvarchar(20),
    tipo_residencia             nvarchar(20),
    constraint UQ_visita_paciente_numero
        unique (id_paciente, numero_visita)
);

create table dbo.diagnostico_paciente
(
    id_diagnostico_paciente        bigint identity
        primary key,
    id_paciente                    bigint not null
        constraint FK_diag_paciente
            references dbo.paciente,
    id_visita_clinica              bigint
        constraint FK_diag_visita
            references dbo.visita_clinica,
    nombre_diagnostico             nvarchar(200),
    estado_cognitivo               nvarchar(50),
    tiene_diagnostico_alzheimer    bit,
    papel_alzheimer_en_diagnostico nvarchar(20),
    fecha_diagnostico              date   not null
);

create table dbo.evaluacion_paciente
(
    id_evaluacion_paciente  bigint identity
        primary key,
    id_paciente             bigint       not null
        constraint FK_eval_paciente
            references dbo.paciente,
    id_visita_clinica       bigint
        constraint FK_eval_visita
            references dbo.visita_clinica,
    id_participacion_sesion bigint
        constraint FK_eval_participacion
            references dbo.participacion_sesion,
    id_exposicion_musical   bigint
        constraint FK_eval_exposicion
            references dbo.exposicion_musical,
    momento_evaluacion      nvarchar(50),
    condicion_evaluada      nvarchar(60),
    nivel_evaluacion        nvarchar(30) not null,
    fecha_hora_evaluacion   datetime2(6) not null
);

create table dbo.medicamento_paciente_visita
(
    id_medicamento_paciente_visita bigint identity
        primary key,
    id_visita_clinica              bigint not null
        constraint FK_medvis_visita
            references dbo.visita_clinica,
    id_medicamento                 bigint not null
        constraint FK_medvis_medicamento
            references dbo.medicamento,
    constraint UQ_visita_medicamento
        unique (id_visita_clinica, id_medicamento)
);

create table dbo.resultado_evaluacion
(
    id_resultado_evaluacion   bigint identity
        primary key,
    id_evaluacion_paciente    bigint not null
        constraint FK_reseval_evaluacion
            references dbo.evaluacion_paciente,
    id_instrumento_evaluacion bigint not null
        constraint FK_reseval_instrumento
            references dbo.instrumento_evaluacion,
    puntuacion_obtenida       decimal(18, 6),
    motivo_sin_puntuacion     nvarchar(30),
    forma_calculo_puntuacion  nvarchar(100)
);

create table dbo.sintoma_visita
(
    id_sintoma_visita bigint identity
        primary key,
    id_visita_clinica bigint       not null
        constraint FK_sintoma_visita
            references dbo.visita_clinica,
    nombre_sintoma    nvarchar(60) not null,
    presenta_sintoma  bit,
    severidad_sintoma nvarchar(20),
    constraint UQ_visita_sintoma
        unique (id_visita_clinica, nombre_sintoma)
);


	CREATE FUNCTION dbo.fn_diagramobjects() 
	RETURNS int
	WITH EXECUTE AS N'dbo'
	AS
	BEGIN
		declare @id_upgraddiagrams		int
		declare @id_sysdiagrams			int
		declare @id_helpdiagrams		int
		declare @id_helpdiagramdefinition	int
		declare @id_creatediagram	int
		declare @id_renamediagram	int
		declare @id_alterdiagram 	int 
		declare @id_dropdiagram		int
		declare @InstalledObjects	int

		select @InstalledObjects = 0

		select 	@id_upgraddiagrams = object_id(N'dbo.sp_upgraddiagrams'),
			@id_sysdiagrams = object_id(N'dbo.sysdiagrams'),
			@id_helpdiagrams = object_id(N'dbo.sp_helpdiagrams'),
			@id_helpdiagramdefinition = object_id(N'dbo.sp_helpdiagramdefinition'),
			@id_creatediagram = object_id(N'dbo.sp_creatediagram'),
			@id_renamediagram = object_id(N'dbo.sp_renamediagram'),
			@id_alterdiagram = object_id(N'dbo.sp_alterdiagram'), 
			@id_dropdiagram = object_id(N'dbo.sp_dropdiagram')

		if @id_upgraddiagrams is not null
			select @InstalledObjects = @InstalledObjects + 1
		if @id_sysdiagrams is not null
			select @InstalledObjects = @InstalledObjects + 2
		if @id_helpdiagrams is not null
			select @InstalledObjects = @InstalledObjects + 4
		if @id_helpdiagramdefinition is not null
			select @InstalledObjects = @InstalledObjects + 8
		if @id_creatediagram is not null
			select @InstalledObjects = @InstalledObjects + 16
		if @id_renamediagram is not null
			select @InstalledObjects = @InstalledObjects + 32
		if @id_alterdiagram  is not null
			select @InstalledObjects = @InstalledObjects + 64
		if @id_dropdiagram is not null
			select @InstalledObjects = @InstalledObjects + 128
		
		return @InstalledObjects 
	END
;

exec sp_addextendedproperty 'microsoft_database_tools_support', 1, 'SCHEMA', 'dbo', 'FUNCTION', 'fn_diagramobjects';


	CREATE PROCEDURE dbo.sp_alterdiagram
	(
		@diagramname 	sysname,
		@owner_id	int	= null,
		@version 	int,
		@definition 	varbinary(max)
	)
	WITH EXECUTE AS 'dbo'
	AS
	BEGIN
		set nocount on
	
		declare @theId 			int
		declare @retval 		int
		declare @IsDbo 			int
		
		declare @UIDFound 		int
		declare @DiagId			int
		declare @ShouldChangeUID	int
	
		if(@diagramname is null)
		begin
			RAISERROR ('Invalid ARG', 16, 1)
			return -1
		end
	
		execute as caller;
		select @theId = DATABASE_PRINCIPAL_ID();	 
		select @IsDbo = IS_MEMBER(N'db_owner'); 
		if(@owner_id is null)
			select @owner_id = @theId;
		revert;
	
		select @ShouldChangeUID = 0
		select @DiagId = diagram_id, @UIDFound = principal_id from dbo.sysdiagrams where principal_id = @owner_id and name = @diagramname 
		
		if(@DiagId IS NULL or (@IsDbo = 0 and @theId <> @UIDFound))
		begin
			RAISERROR ('Diagram does not exist or you do not have permission.', 16, 1);
			return -3
		end
	
		if(@IsDbo <> 0)
		begin
			if(@UIDFound is null or USER_NAME(@UIDFound) is null) -- invalid principal_id
			begin
				select @ShouldChangeUID = 1 ;
			end
		end

		-- update dds data			
		update dbo.sysdiagrams set definition = @definition where diagram_id = @DiagId ;

		-- change owner
		if(@ShouldChangeUID = 1)
			update dbo.sysdiagrams set principal_id = @theId where diagram_id = @DiagId ;

		-- update dds version
		if(@version is not null)
			update dbo.sysdiagrams set version = @version where diagram_id = @DiagId ;

		return 0
	END
;

exec sp_addextendedproperty 'microsoft_database_tools_support', 1, 'SCHEMA', 'dbo', 'PROCEDURE', 'sp_alterdiagram';


	CREATE PROCEDURE dbo.sp_creatediagram
	(
		@diagramname 	sysname,
		@owner_id		int	= null, 	
		@version 		int,
		@definition 	varbinary(max)
	)
	WITH EXECUTE AS 'dbo'
	AS
	BEGIN
		set nocount on
	
		declare @theId int
		declare @retval int
		declare @IsDbo	int
		declare @userName sysname
		if(@version is null or @diagramname is null)
		begin
			RAISERROR (N'E_INVALIDARG', 16, 1);
			return -1
		end
	
		execute as caller;
		select @theId = DATABASE_PRINCIPAL_ID(); 
		select @IsDbo = IS_MEMBER(N'db_owner');
		revert; 
		
		if @owner_id is null
		begin
			select @owner_id = @theId;
		end
		else
		begin
			if @theId <> @owner_id
			begin
				if @IsDbo = 0
				begin
					RAISERROR (N'E_INVALIDARG', 16, 1);
					return -1
				end
				select @theId = @owner_id
			end
		end
		-- next 2 line only for test, will be removed after define name unique
		if EXISTS(select diagram_id from dbo.sysdiagrams where principal_id = @theId and name = @diagramname)
		begin
			RAISERROR ('The name is already used.', 16, 1);
			return -2
		end
	
		insert into dbo.sysdiagrams(name, principal_id , version, definition)
				VALUES(@diagramname, @theId, @version, @definition) ;
		
		select @retval = @@IDENTITY 
		return @retval
	END
;

exec sp_addextendedproperty 'microsoft_database_tools_support', 1, 'SCHEMA', 'dbo', 'PROCEDURE', 'sp_creatediagram';


	CREATE PROCEDURE dbo.sp_dropdiagram
	(
		@diagramname 	sysname,
		@owner_id	int	= null
	)
	WITH EXECUTE AS 'dbo'
	AS
	BEGIN
		set nocount on
		declare @theId 			int
		declare @IsDbo 			int
		
		declare @UIDFound 		int
		declare @DiagId			int
	
		if(@diagramname is null)
		begin
			RAISERROR ('Invalid value', 16, 1);
			return -1
		end
	
		EXECUTE AS CALLER;
		select @theId = DATABASE_PRINCIPAL_ID();
		select @IsDbo = IS_MEMBER(N'db_owner'); 
		if(@owner_id is null)
			select @owner_id = @theId;
		REVERT; 
		
		select @DiagId = diagram_id, @UIDFound = principal_id from dbo.sysdiagrams where principal_id = @owner_id and name = @diagramname 
		if(@DiagId IS NULL or (@IsDbo = 0 and @UIDFound <> @theId))
		begin
			RAISERROR ('Diagram does not exist or you do not have permission.', 16, 1)
			return -3
		end
	
		delete from dbo.sysdiagrams where diagram_id = @DiagId;
	
		return 0;
	END
;

exec sp_addextendedproperty 'microsoft_database_tools_support', 1, 'SCHEMA', 'dbo', 'PROCEDURE', 'sp_dropdiagram';


	CREATE PROCEDURE dbo.sp_helpdiagramdefinition
	(
		@diagramname 	sysname,
		@owner_id	int	= null 		
	)
	WITH EXECUTE AS N'dbo'
	AS
	BEGIN
		set nocount on

		declare @theId 		int
		declare @IsDbo 		int
		declare @DiagId		int
		declare @UIDFound	int
	
		if(@diagramname is null)
		begin
			RAISERROR (N'E_INVALIDARG', 16, 1);
			return -1
		end
	
		execute as caller;
		select @theId = DATABASE_PRINCIPAL_ID();
		select @IsDbo = IS_MEMBER(N'db_owner');
		if(@owner_id is null)
			select @owner_id = @theId;
		revert; 
	
		select @DiagId = diagram_id, @UIDFound = principal_id from dbo.sysdiagrams where principal_id = @owner_id and name = @diagramname;
		if(@DiagId IS NULL or (@IsDbo = 0 and @UIDFound <> @theId ))
		begin
			RAISERROR ('Diagram does not exist or you do not have permission.', 16, 1);
			return -3
		end

		select version, definition FROM dbo.sysdiagrams where diagram_id = @DiagId ; 
		return 0
	END
;

exec sp_addextendedproperty 'microsoft_database_tools_support', 1, 'SCHEMA', 'dbo', 'PROCEDURE',
     'sp_helpdiagramdefinition';


	CREATE PROCEDURE dbo.sp_helpdiagrams
	(
		@diagramname sysname = NULL,
		@owner_id int = NULL
	)
	WITH EXECUTE AS N'dbo'
	AS
	BEGIN
		DECLARE @user sysname
		DECLARE @dboLogin bit
		EXECUTE AS CALLER;
			SET @user = USER_NAME();
			SET @dboLogin = CONVERT(bit,IS_MEMBER('db_owner'));
		REVERT;
		SELECT
			[Database] = DB_NAME(),
			[Name] = name,
			[ID] = diagram_id,
			[Owner] = USER_NAME(principal_id),
			[OwnerID] = principal_id
		FROM
			sysdiagrams
		WHERE
			(@dboLogin = 1 OR USER_NAME(principal_id) = @user) AND
			(@diagramname IS NULL OR name = @diagramname) AND
			(@owner_id IS NULL OR principal_id = @owner_id)
		ORDER BY
			4, 5, 1
	END
;

exec sp_addextendedproperty 'microsoft_database_tools_support', 1, 'SCHEMA', 'dbo', 'PROCEDURE', 'sp_helpdiagrams';


	CREATE PROCEDURE dbo.sp_renamediagram
	(
		@diagramname 		sysname,
		@owner_id		int	= null,
		@new_diagramname	sysname
	
	)
	WITH EXECUTE AS 'dbo'
	AS
	BEGIN
		set nocount on
		declare @theId 			int
		declare @IsDbo 			int
		
		declare @UIDFound 		int
		declare @DiagId			int
		declare @DiagIdTarg		int
		declare @u_name			sysname
		if((@diagramname is null) or (@new_diagramname is null))
		begin
			RAISERROR ('Invalid value', 16, 1);
			return -1
		end
	
		EXECUTE AS CALLER;
		select @theId = DATABASE_PRINCIPAL_ID();
		select @IsDbo = IS_MEMBER(N'db_owner'); 
		if(@owner_id is null)
			select @owner_id = @theId;
		REVERT;
	
		select @u_name = USER_NAME(@owner_id)
	
		select @DiagId = diagram_id, @UIDFound = principal_id from dbo.sysdiagrams where principal_id = @owner_id and name = @diagramname 
		if(@DiagId IS NULL or (@IsDbo = 0 and @UIDFound <> @theId))
		begin
			RAISERROR ('Diagram does not exist or you do not have permission.', 16, 1)
			return -3
		end
	
		-- if((@u_name is not null) and (@new_diagramname = @diagramname))	-- nothing will change
		--	return 0;
	
		if(@u_name is null)
			select @DiagIdTarg = diagram_id from dbo.sysdiagrams where principal_id = @theId and name = @new_diagramname
		else
			select @DiagIdTarg = diagram_id from dbo.sysdiagrams where principal_id = @owner_id and name = @new_diagramname
	
		if((@DiagIdTarg is not null) and  @DiagId <> @DiagIdTarg)
		begin
			RAISERROR ('The name is already used.', 16, 1);
			return -2
		end		
	
		if(@u_name is null)
			update dbo.sysdiagrams set [name] = @new_diagramname, principal_id = @theId where diagram_id = @DiagId
		else
			update dbo.sysdiagrams set [name] = @new_diagramname where diagram_id = @DiagId
		return 0
	END
;

exec sp_addextendedproperty 'microsoft_database_tools_support', 1, 'SCHEMA', 'dbo', 'PROCEDURE', 'sp_renamediagram';


	CREATE PROCEDURE dbo.sp_upgraddiagrams
	AS
	BEGIN
		IF OBJECT_ID(N'dbo.sysdiagrams') IS NOT NULL
			return 0;
	
		CREATE TABLE dbo.sysdiagrams
		(
			name sysname NOT NULL,
			principal_id int NOT NULL,	-- we may change it to varbinary(85)
			diagram_id int PRIMARY KEY IDENTITY,
			version int,
	
			definition varbinary(max)
			CONSTRAINT UK_principal_name UNIQUE
			(
				principal_id,
				name
			)
		);


		/* Add this if we need to have some form of extended properties for diagrams */
		/*
		IF OBJECT_ID(N'dbo.sysdiagram_properties') IS NULL
		BEGIN
			CREATE TABLE dbo.sysdiagram_properties
			(
				diagram_id int,
				name sysname,
				value varbinary(max) NOT NULL
			)
		END
		*/

		IF OBJECT_ID(N'dbo.dtproperties') IS NOT NULL
		begin
			insert into dbo.sysdiagrams
			(
				[name],
				[principal_id],
				[version],
				[definition]
			)
			select	 
				convert(sysname, dgnm.[uvalue]),
				DATABASE_PRINCIPAL_ID(N'dbo'),			-- will change to the sid of sa
				0,							-- zero for old format, dgdef.[version],
				dgdef.[lvalue]
			from dbo.[dtproperties] dgnm
				inner join dbo.[dtproperties] dggd on dggd.[property] = 'DtgSchemaGUID' and dggd.[objectid] = dgnm.[objectid]	
				inner join dbo.[dtproperties] dgdef on dgdef.[property] = 'DtgSchemaDATA' and dgdef.[objectid] = dgnm.[objectid]
				
			where dgnm.[property] = 'DtgSchemaNAME' and dggd.[uvalue] like N'_EA3E6268-D998-11CE-9454-00AA00A3F36E_' 
			return 2;
		end
		return 1;
	END
;

exec sp_addextendedproperty 'microsoft_database_tools_support', 1, 'SCHEMA', 'dbo', 'PROCEDURE', 'sp_upgraddiagrams';

