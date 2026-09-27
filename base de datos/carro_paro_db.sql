-- =====================================================================
-- SMARTDATA 360 · Módulo Carro de Paro — Esquema v2
-- Proyecto integrador Big Data (Corte II)
--
-- Cambios frente a v1 (carro_paro_db_v1_anterior.sql):
--   * Roles y permisos en tablas (RBAC por permiso, no por lista de roles).
--   * Usuarios con bloqueo por intentos fallidos y cambio obligatorio de clave.
--   * Carros y servicios: el inventario pertenece a un carro concreto.
--   * inventario_carro guarda LOTES con cantidad (antes: una fila por unidad).
--   * movimientos: consumos, ingresos y bajas -> fuente de la analítica.
--   * alertas: se corrigen los nombres de columna usados por la app
--     (v1 consultaba 'resuelta'/'fecha_creacion', que no existían).
--   * log_auditoria.accion pasa de ENUM a VARCHAR (v1 fallaba al registrar
--     CREACION_USUARIO porque no estaba en el ENUM).
--   * Nuevas: eventos_seguridad, predicciones_demanda; consultas_agente ampliada.
--
-- Usuarios, roles, permisos, carros y catálogo NO se insertan aquí:
-- se cargan con  python scripts/inicializar_bd.py  para que las contraseñas
-- queden con bcrypt y la matriz de permisos tenga una sola fuente de verdad
-- (src/seguridad/permisos.py).
-- =====================================================================

DROP DATABASE IF EXISTS carro_paro_db;
CREATE DATABASE carro_paro_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE carro_paro_db;

-- ---------------------------------------------------------------------
-- Seguridad y control de acceso
-- ---------------------------------------------------------------------
CREATE TABLE roles (
    codigo       VARCHAR(30) PRIMARY KEY,
    nombre       VARCHAR(80) NOT NULL,
    descripcion  VARCHAR(255)
) ENGINE=InnoDB;

CREATE TABLE permisos (
    codigo       VARCHAR(50) PRIMARY KEY,
    descripcion  VARCHAR(255) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE rol_permiso (
    rol      VARCHAR(30) NOT NULL,
    permiso  VARCHAR(50) NOT NULL,
    PRIMARY KEY (rol, permiso),
    CONSTRAINT fk_rp_rol     FOREIGN KEY (rol)     REFERENCES roles(codigo)    ON DELETE CASCADE,
    CONSTRAINT fk_rp_permiso FOREIGN KEY (permiso) REFERENCES permisos(codigo) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE usuarios (
    id                     INT AUTO_INCREMENT PRIMARY KEY,
    nombre                 VARCHAR(120) NOT NULL,
    correo                 VARCHAR(150) NOT NULL UNIQUE,
    password_hash          VARCHAR(255) NOT NULL,
    rol                    VARCHAR(30)  NOT NULL,
    activo                 TINYINT      NOT NULL DEFAULT 1,
    intentos_fallidos      INT          NOT NULL DEFAULT 0,
    bloqueado_hasta        DATETIME     NULL,
    debe_cambiar_password  TINYINT      NOT NULL DEFAULT 1,
    ultimo_acceso          DATETIME     NULL,
    fecha_creacion         DATETIME     DEFAULT CURRENT_TIMESTAMP,
    -- Segundo factor (TOTP)
    totp_secret            VARCHAR(64)  NULL,
    mfa_activo             TINYINT      NOT NULL DEFAULT 0,
    mfa_confirmado         TINYINT      NOT NULL DEFAULT 0,
    totp_ultimo_intervalo  BIGINT       NULL,
    CONSTRAINT fk_usuarios_rol FOREIGN KEY (rol) REFERENCES roles(codigo)
) ENGINE=InnoDB;

-- Evidencia de la aceptación de las políticas (Ley 1581 de 2012, art. 9)
CREATE TABLE consentimientos (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    usuario_id  INT NOT NULL,
    version     VARCHAR(20) NOT NULL,
    documento   VARCHAR(40) NOT NULL DEFAULT 'politicas',
    origen      VARCHAR(20) NOT NULL DEFAULT 'WEB',
    fecha       DATETIME DEFAULT CURRENT_TIMESTAMP,
    revocado    TINYINT NOT NULL DEFAULT 0,
    fecha_revocacion DATETIME NULL,
    CONSTRAINT fk_consent_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    INDEX idx_consent_usuario (usuario_id, version, revocado)
) ENGINE=InnoDB;

-- Códigos de un solo uso para recuperar el acceso si se pierde el celular
CREATE TABLE codigos_respaldo (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id     INT NOT NULL,
    codigo_hash    VARCHAR(255) NOT NULL,
    usado          TINYINT NOT NULL DEFAULT 0,
    fecha_uso      DATETIME NULL,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_respaldo_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    INDEX idx_respaldo_usuario (usuario_id, usado)
) ENGINE=InnoDB;

CREATE TABLE eventos_seguridad (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    usuario_id  INT NULL,
    correo      VARCHAR(150),
    tipo        VARCHAR(40) NOT NULL,   -- LOGIN_OK, LOGIN_FALLIDO, BLOQUEO, LOGOUT, SESION_EXPIRADA, ACCESO_DENEGADO, CAMBIO_PASSWORD, DESBLOQUEO
    origen      VARCHAR(20) NOT NULL DEFAULT 'WEB',  -- WEB | API | AGENTE
    detalle     VARCHAR(255),
    fecha       DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_seg_fecha (fecha),
    INDEX idx_seg_tipo (tipo)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Estructura hospitalaria
-- ---------------------------------------------------------------------
CREATE TABLE servicios (
    id      INT AUTO_INCREMENT PRIMARY KEY,
    nombre  VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE carros (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    codigo       VARCHAR(20) NOT NULL UNIQUE,
    servicio_id  INT NOT NULL,
    ubicacion    VARCHAR(120),
    activo       TINYINT NOT NULL DEFAULT 1,
    CONSTRAINT fk_carros_servicio FOREIGN KEY (servicio_id) REFERENCES servicios(id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Medicamentos e inventario
-- ---------------------------------------------------------------------
CREATE TABLE cat_medicamentos (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    nombre           VARCHAR(150) NOT NULL UNIQUE,
    principio_activo VARCHAR(120),
    codigo_cum       VARCHAR(40),
    descripcion      TEXT,
    criticidad       ENUM('ALTA', 'MEDIA', 'BAJA') DEFAULT 'ALTA',
    stock_minimo     INT NOT NULL DEFAULT 2,     -- unidades mínimas por carro
    stock_maximo     INT NOT NULL DEFAULT 6,     -- dotación completa por carro
    costo_unitario   DECIMAL(12,2) NOT NULL DEFAULT 0,
    activo           TINYINT NOT NULL DEFAULT 1
) ENGINE=InnoDB;

CREATE TABLE inventario_carro (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    carro_id             INT NOT NULL,
    medicamento_id       INT NOT NULL,
    usuario_id           INT NOT NULL,
    lote                 VARCHAR(60) NOT NULL,
    cantidad             INT NOT NULL DEFAULT 0,
    fecha_registro       DATETIME DEFAULT CURRENT_TIMESTAMP,
    fecha_vencimiento    DATE NOT NULL,
    estado               ENUM('vigente', 'proximo_a_vencer', 'vencido', 'agotado', 'dado_de_baja') DEFAULT 'vigente',
    origen_registro      ENUM('MANUAL', 'OCR', 'MIGRACION') DEFAULT 'MANUAL',
    imagen_ruta          VARCHAR(255),
    confianza_deteccion  FLOAT,
    confianza_ocr        FLOAT,
    editado_manual       TINYINT DEFAULT 0,
    CONSTRAINT fk_inv_carro       FOREIGN KEY (carro_id)       REFERENCES carros(id),
    CONSTRAINT fk_inv_medicamento FOREIGN KEY (medicamento_id) REFERENCES cat_medicamentos(id),
    CONSTRAINT fk_inv_usuario     FOREIGN KEY (usuario_id)     REFERENCES usuarios(id),
    CONSTRAINT chk_inv_cantidad CHECK (cantidad >= 0),
    INDEX idx_inv_venc (fecha_vencimiento),
    INDEX idx_inv_estado (estado)
) ENGINE=InnoDB;

-- Cada entrada o salida de unidades. Es la tabla transaccional que alimenta
-- el pipeline Big Data (consumo histórico, rotación, predicción).
CREATE TABLE movimientos (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    inventario_id      INT NULL,
    carro_id           INT NOT NULL,
    medicamento_id     INT NOT NULL,
    usuario_id         INT NOT NULL,
    tipo               ENUM('INGRESO', 'CONSUMO', 'BAJA_VENCIMIENTO', 'AJUSTE') NOT NULL,
    cantidad           INT NOT NULL,
    motivo             VARCHAR(255),
    evento_codigo_azul TINYINT NOT NULL DEFAULT 0,
    fecha              DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_mov_inventario  FOREIGN KEY (inventario_id)  REFERENCES inventario_carro(id),
    CONSTRAINT fk_mov_carro       FOREIGN KEY (carro_id)       REFERENCES carros(id),
    CONSTRAINT fk_mov_medicamento FOREIGN KEY (medicamento_id) REFERENCES cat_medicamentos(id),
    CONSTRAINT fk_mov_usuario     FOREIGN KEY (usuario_id)     REFERENCES usuarios(id),
    INDEX idx_mov_fecha (fecha)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Alertas, riesgo y analítica
-- ---------------------------------------------------------------------
CREATE TABLE alertas (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    inventario_id   INT NULL,
    carro_id        INT NULL,
    medicamento_id  INT NULL,
    tipo            ENUM('PROXIMO_VENCER', 'VENCIDO', 'STOCK_BAJO', 'RIESGO_DESABASTECIMIENTO',
                         'CONSUMO_ANOMALO', 'RECOMENDACION_AGENTE') NOT NULL,
    severidad       ENUM('ALTA', 'MEDIA', 'BAJA') NOT NULL DEFAULT 'MEDIA',
    mensaje         VARCHAR(255),
    origen          ENUM('SISTEMA', 'ANALITICA', 'AGENTE') NOT NULL DEFAULT 'SISTEMA',
    fecha_generada  DATETIME DEFAULT CURRENT_TIMESTAMP,
    atendida        TINYINT NOT NULL DEFAULT 0,
    atendida_por    INT NULL,
    fecha_atencion  DATETIME NULL,
    nota_atencion   VARCHAR(255),
    CONSTRAINT fk_alertas_inventario  FOREIGN KEY (inventario_id)  REFERENCES inventario_carro(id),
    CONSTRAINT fk_alertas_carro       FOREIGN KEY (carro_id)       REFERENCES carros(id),
    CONSTRAINT fk_alertas_medicamento FOREIGN KEY (medicamento_id) REFERENCES cat_medicamentos(id),
    CONSTRAINT fk_alertas_usuario     FOREIGN KEY (atendida_por)   REFERENCES usuarios(id),
    INDEX idx_alertas_pend (atendida, tipo)
) ENGINE=InnoDB;

CREATE TABLE historial_riesgo (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    carro_id          INT NOT NULL,
    medicamento_id    INT NOT NULL,
    fecha_evaluacion  DATETIME DEFAULT CURRENT_TIMESTAMP,
    probabilidad      INT,          -- 1..5
    impacto           INT,          -- 1..5
    puntaje_riesgo    INT,          -- probabilidad * impacto
    nivel_riesgo      ENUM('ALTO', 'MEDIO', 'BAJO') DEFAULT 'MEDIO',
    justificacion     VARCHAR(255),
    CONSTRAINT fk_riesgo_carro       FOREIGN KEY (carro_id)       REFERENCES carros(id),
    CONSTRAINT fk_riesgo_medicamento FOREIGN KEY (medicamento_id) REFERENCES cat_medicamentos(id)
) ENGINE=InnoDB;

CREATE TABLE predicciones_demanda (
    id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
    fecha_ejecucion    DATETIME DEFAULT CURRENT_TIMESTAMP,
    carro_id           INT NOT NULL,
    medicamento_id     INT NOT NULL,
    horizonte_dias     INT NOT NULL,
    demanda_estimada   DECIMAL(10,2) NOT NULL,
    stock_actual       INT NOT NULL,
    dias_cobertura     DECIMAL(10,1),
    riesgo_desabastecimiento TINYINT NOT NULL DEFAULT 0,
    CONSTRAINT fk_pred_carro       FOREIGN KEY (carro_id)       REFERENCES carros(id),
    CONSTRAINT fk_pred_medicamento FOREIGN KEY (medicamento_id) REFERENCES cat_medicamentos(id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Trazabilidad
-- ---------------------------------------------------------------------
CREATE TABLE log_auditoria (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    usuario_id  INT NULL,
    accion      VARCHAR(40) NOT NULL,   -- INSERCION, ACTUALIZACION, BAJA, CONSUMO, CREACION_USUARIO, LECTURA_OCR, CONSULTA_AGENTE, ACCION_AGENTE, EJECUCION_PIPELINE ...
    entidad     VARCHAR(60) NOT NULL,
    entidad_id  BIGINT,
    origen      VARCHAR(20) NOT NULL DEFAULT 'WEB',
    fecha       DATETIME DEFAULT CURRENT_TIMESTAMP,
    detalle     VARCHAR(500),
    CONSTRAINT fk_auditoria_usuarios FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
    INDEX idx_aud_fecha (fecha)
) ENGINE=InnoDB;

CREATE TABLE consultas_agente (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    usuario_id          INT NOT NULL,
    pregunta            TEXT NOT NULL,
    respuesta           TEXT NOT NULL,
    herramientas_usadas VARCHAR(500),
    proveedor           VARCHAR(40),
    fecha               DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_consultas_usuarios FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;
