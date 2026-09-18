-- 1. Crear y seleccionar la base de datos desde cero
DROP DATABASE IF EXISTS carro_paro_db;
CREATE DATABASE carro_paro_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE carro_paro_db;

-- 2. Tabla de Usuarios (Seguridad y Control de Acceso)
CREATE TABLE usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    correo VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol ENUM('ADMINISTRADOR', 'ENFERMERO', 'AUDITOR') DEFAULT 'ENFERMERO',
    activo TINYINT DEFAULT 1,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 3. Tabla Catálogo Maestro de Medicamentos (Información Genérica)
CREATE TABLE cat_medicamentos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL UNIQUE,
    descripcion TEXT,
    criticidad ENUM('ALTA', 'MEDIA', 'BAJA') DEFAULT 'ALTA'
) ENGINE=InnoDB;

-- 4. Tabla de Inventario de Medicamentos (Unidades Físicas en el Carro)
CREATE TABLE inventario_carro (
    id INT AUTO_INCREMENT PRIMARY KEY,
    medicamento_id INT NOT NULL,
    usuario_id INT NOT NULL,
    lote VARCHAR(60),
    fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
    fecha_vencimiento DATE,
    estado ENUM('vigente', 'proximo_a_vencer', 'vencido') DEFAULT 'vigente',
    imagen_ruta VARCHAR(255),
    confianza_deteccion FLOAT,
    confianza_ocr FLOAT,
    editado_manual TINYINT DEFAULT 0,
    CONSTRAINT fk_inventario_cat_medicamentos 
        FOREIGN KEY (medicamento_id) REFERENCES cat_medicamentos(id) ON DELETE CASCADE,
    CONSTRAINT fk_inventario_usuarios 
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;

-- 5. Tabla de Alertas (Notificaciones automáticas por inventario)
CREATE TABLE alertas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    medicamento_id INT NOT NULL,
    tipo ENUM('PROXIMO_VENCER', 'VENCIDO', 'STOCK_BAJO') NOT NULL,
    fecha_generada DATETIME DEFAULT CURRENT_TIMESTAMP,
    atendida TINYINT DEFAULT 0,
    CONSTRAINT fk_alertas_inventario 
        FOREIGN KEY (medicamento_id) REFERENCES inventario_carro(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 6. Tabla de Historial de Riesgo (Evaluación analítica y estadística)
CREATE TABLE historial_riesgo (
    id INT AUTO_INCREMENT PRIMARY KEY,
    medicamento_id INT NOT NULL,
    fecha_evaluacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    probabilidad INT,
    impacto INT,
    puntaje_riesgo INT,
    nivel_riesgo ENUM('ALTO', 'MEDIO', 'BAJO') DEFAULT 'MEDIO',
    CONSTRAINT fk_riesgo_inventario 
        FOREIGN KEY (medicamento_id) REFERENCES inventario_carro(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 7. Tabla Log de Auditoría (Trazabilidad de acciones del sistema)
CREATE TABLE log_auditoria (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    accion ENUM('INSERCION', 'ACTUALIZACION', 'ELIMINACION', 'LECTURA_OCR', 'CONSULTA_AGENTE') NOT NULL,
    entidad VARCHAR(60) NOT NULL,
    entidad_id INT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    detalle VARCHAR(255),
    CONSTRAINT fk_auditoria_usuarios 
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;

-- 8. Tabla de Consultas del Agente de IA (Historial de interacción conversacional)
CREATE TABLE consultas_agente (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    pregunta TEXT NOT NULL,
    respuesta TEXT NOT NULL,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_consultas_usuarios 
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
) ENGINE=InnoDB;

USE carro_paro_db;

-- 1. Insertar usuario enfermero de prueba
INSERT IGNORE INTO usuarios (id, nombre, correo, password_hash, rol) 
VALUES (1, 'Enfermero de Turno', 'enfermero@hospital.com', 'hash_demo_123', 'ENFERMERO');

-- 2. Insertar catálogo de medicamentos para el carro de paro
INSERT IGNORE INTO cat_medicamentos (id, nombre, descripcion, criticidad) VALUES 
(1, 'Adrenalina 1mg/ml', 'Ampolla 1ml - Paro cardiorrespiratorio', 'ALTA'),
(2, 'Atropina 1mg/ml', 'Ampolla 1ml - Bradicardia sintomática', 'ALTA'),
(3, 'Amiodarona 150mg/3ml', 'Ampolla 3ml - Arritmias ventriculares', 'ALTA'),
(4, 'Bicarbonato de Sodio 10%', 'Ampolla 10ml - Acidosis metabólica', 'MEDIA'),
(5, 'Sulfato de Magnesio 20%', 'Ampolla 10ml - Torsade de pointes / Eclampsia', 'MEDIA');


SELECT * FROM carro_paro_db.alertas;


USE carro_paro_db;

-- Insertar o actualizar usuarios de prueba con hash SHA-256
-- Contraseña para todos los usuarios de prueba: 123456
-- Hash SHA-256 de '123456': 8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92

USE carro_paro_db;

INSERT INTO usuarios (id, nombre, correo, password_hash, rol, activo) VALUES
(1, 'Carlos Enfermero', 'enfermero@hospital.com', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 'ENFERMERO', 1),
(2, 'Dra. Elena Admin', 'admin@hospital.com', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 'ADMINISTRADOR', 1),
(3, 'Roberto Auditor', 'auditor@hospital.com', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92', 'AUDITOR', 1)
AS new_val
ON DUPLICATE KEY UPDATE 
    password_hash = new_val.password_hash,
    rol = new_val.rol;