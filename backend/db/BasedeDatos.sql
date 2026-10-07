-- ============================================================
-- ICOPE - MODELO FÍSICO DE BASE DE DATOS
-- MariaDB
-- Modelo relacional normalizado hasta 3FN
-- ============================================================

DROP DATABASE IF EXISTS icope;
CREATE DATABASE icope
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE icope;

-- ============================================================
-- 1. USUARIOS Y ROLES
-- ============================================================

CREATE TABLE usuario (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    telefono VARCHAR(30),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;


CREATE TABLE rol (
    id_rol INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;


CREATE TABLE usuario_rol (
    id_usuario INT NOT NULL,
    id_rol INT NOT NULL,

    PRIMARY KEY (id_usuario, id_rol),

    CONSTRAINT fk_usuario_rol_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_usuario_rol_rol
        FOREIGN KEY (id_rol)
        REFERENCES rol(id_rol)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE=InnoDB;


-- ============================================================
-- 2. CATÁLOGO
-- ============================================================

CREATE TABLE categoria (
    id_categoria INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion VARCHAR(255)
) ENGINE=InnoDB;


CREATE TABLE producto (
    id_producto INT AUTO_INCREMENT PRIMARY KEY,
    id_categoria INT NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT,
    precio DECIMAL(10,2) NOT NULL,
    es_evento BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_evento DATETIME NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_producto_categoria
        FOREIGN KEY (id_categoria)
        REFERENCES categoria(id_categoria)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT chk_producto_precio
        CHECK (precio >= 0),

    CONSTRAINT chk_producto_evento
        CHECK (
            (es_evento = FALSE AND fecha_evento IS NULL)
            OR
            (es_evento = TRUE AND fecha_evento IS NOT NULL)
        )
) ENGINE=InnoDB;


-- Las variantes permiten manejar talles, modelos, etc.
-- Un producto puede tener una o muchas variantes.
CREATE TABLE variante_producto (
    id_variante INT AUTO_INCREMENT PRIMARY KEY,
    id_producto INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    stock INT NOT NULL DEFAULT 0,

    CONSTRAINT uq_variante_producto
        UNIQUE (id_producto, nombre),

    CONSTRAINT fk_variante_producto
        FOREIGN KEY (id_producto)
        REFERENCES producto(id_producto)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT chk_variante_stock
        CHECK (stock >= 0)
) ENGINE=InnoDB;


-- Galería de imágenes de productos
CREATE TABLE producto_imagen (
    id_imagen INT AUTO_INCREMENT PRIMARY KEY,
    id_producto INT NOT NULL,
    url_imagen VARCHAR(500) NOT NULL,
    orden INT NOT NULL DEFAULT 1,

    CONSTRAINT uq_producto_imagen_orden
        UNIQUE (id_producto, orden),

    CONSTRAINT fk_imagen_producto
        FOREIGN KEY (id_producto)
        REFERENCES producto(id_producto)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT chk_imagen_orden
        CHECK (orden > 0)
) ENGINE=InnoDB;


-- ============================================================
-- 3. CARRITO
-- ============================================================

CREATE TABLE carrito (
    id_carrito INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,
    estado ENUM(
        'ACTIVO',
        'CONVERTIDO',
        'ABANDONADO'
    ) NOT NULL DEFAULT 'ACTIVO',
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_carrito_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB;


CREATE TABLE detalle_carrito (
    id_detalle_carrito INT AUTO_INCREMENT PRIMARY KEY,
    id_carrito INT NOT NULL,
    id_variante INT NOT NULL,
    cantidad INT NOT NULL,

    CONSTRAINT uq_carrito_variante
        UNIQUE (id_carrito, id_variante),

    CONSTRAINT fk_detalle_carrito_carrito
        FOREIGN KEY (id_carrito)
        REFERENCES carrito(id_carrito)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_detalle_carrito_variante
        FOREIGN KEY (id_variante)
        REFERENCES variante_producto(id_variante)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT chk_detalle_carrito_cantidad
        CHECK (cantidad > 0)
) ENGINE=InnoDB;


-- ============================================================
-- 4. PEDIDOS
-- ============================================================

CREATE TABLE pedido (
    id_pedido INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,

    estado ENUM(
        'PENDING',
        'APPROVED',
        'REJECTED',
        'CANCELLED',
        'READY',
        'DELIVERED'
    ) NOT NULL DEFAULT 'PENDING',

    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_vencimiento_reserva DATETIME NULL,

    CONSTRAINT fk_pedido_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE=InnoDB;


CREATE TABLE detalle_pedido (
    id_detalle INT AUTO_INCREMENT PRIMARY KEY,
    id_pedido INT NOT NULL,
    id_variante INT NOT NULL,

    cantidad INT NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,

    CONSTRAINT fk_detalle_pedido_pedido
        FOREIGN KEY (id_pedido)
        REFERENCES pedido(id_pedido)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_detalle_pedido_variante
        FOREIGN KEY (id_variante)
        REFERENCES variante_producto(id_variante)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT chk_detalle_pedido_cantidad
        CHECK (cantidad > 0),

    CONSTRAINT chk_detalle_pedido_precio
        CHECK (precio_unitario >= 0)
) ENGINE=InnoDB;


-- ============================================================
-- 5. PAGOS
-- ============================================================

CREATE TABLE pago (
    id_pago INT AUTO_INCREMENT PRIMARY KEY,
    id_pedido INT NOT NULL,

    metodo ENUM(
        'MERCADO_PAGO',
        'TRANSFERENCIA'
    ) NOT NULL,

    estado ENUM(
        'PENDING',
        'APPROVED',
        'REJECTED',
        'CANCELLED'
    ) NOT NULL DEFAULT 'PENDING',

    monto DECIMAL(10,2) NOT NULL,
    referencia VARCHAR(150),
    comprobante VARCHAR(500),
    fecha_pago DATETIME NULL,

    CONSTRAINT fk_pago_pedido
        FOREIGN KEY (id_pedido)
        REFERENCES pedido(id_pedido)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT chk_pago_monto
        CHECK (monto >= 0)
) ENGINE=InnoDB;


-- ============================================================
-- 6. TICKETS QR PARA EVENTOS
-- ============================================================

CREATE TABLE ticket_qr (
    id_ticket INT AUTO_INCREMENT PRIMARY KEY,
    id_detalle INT NOT NULL UNIQUE,

    hash_qr CHAR(64) NOT NULL UNIQUE,

    utilizado BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_generacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_uso DATETIME NULL,

    CONSTRAINT fk_ticket_detalle
        FOREIGN KEY (id_detalle)
        REFERENCES detalle_pedido(id_detalle)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB;


-- ============================================================
-- 7. FORO / NOVEDADES
-- ============================================================

CREATE TABLE publicacion (
    id_publicacion INT AUTO_INCREMENT PRIMARY KEY,
    id_autor INT NOT NULL,

    titulo VARCHAR(200) NOT NULL,
    contenido TEXT NOT NULL,
    urgente BOOLEAN NOT NULL DEFAULT FALSE,
    publicado BOOLEAN NOT NULL DEFAULT TRUE,
    fecha_publicacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_publicacion_autor
        FOREIGN KEY (id_autor)
        REFERENCES usuario(id_usuario)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT chk_publicacion_titulo
        CHECK (CHAR_LENGTH(TRIM(titulo)) > 0),

    CONSTRAINT chk_publicacion_contenido
        CHECK (CHAR_LENGTH(TRIM(contenido)) > 0)
) ENGINE=InnoDB;


-- ============================================================
-- 8. CALENDARIO Y ESPACIOS
-- ============================================================

CREATE TABLE espacio (
    id_espacio INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion VARCHAR(255)
) ENGINE=InnoDB;


CREATE TABLE evento (
    id_evento INT AUTO_INCREMENT PRIMARY KEY,
    id_espacio INT NOT NULL,
    id_creador INT NOT NULL,

    titulo VARCHAR(200) NOT NULL,
    descripcion TEXT,
    tipo VARCHAR(50) NOT NULL,
    fecha_inicio DATETIME NOT NULL,
    fecha_fin DATETIME NOT NULL,

    CONSTRAINT fk_evento_espacio
        FOREIGN KEY (id_espacio)
        REFERENCES espacio(id_espacio)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT fk_evento_creador
        FOREIGN KEY (id_creador)
        REFERENCES usuario(id_usuario)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT chk_evento_fechas
        CHECK (fecha_fin > fecha_inicio)
) ENGINE=InnoDB;


-- ============================================================
-- 9. VOLUNTARIADOS
-- ============================================================

CREATE TABLE franja_voluntariado (
    id_franja INT AUTO_INCREMENT PRIMARY KEY,
    id_evento INT NOT NULL,

    actividad VARCHAR(150) NOT NULL,
    fecha_hora_inicio DATETIME NOT NULL,
    fecha_hora_fin DATETIME NOT NULL,
    cupo INT NOT NULL DEFAULT 1,

    CONSTRAINT fk_franja_evento
        FOREIGN KEY (id_evento)
        REFERENCES evento(id_evento)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT chk_franja_fechas
        CHECK (fecha_hora_fin > fecha_hora_inicio),

    CONSTRAINT chk_franja_cupo
        CHECK (cupo > 0)
) ENGINE=InnoDB;


CREATE TABLE inscripcion_voluntariado (
    id_inscripcion INT AUTO_INCREMENT PRIMARY KEY,
    id_franja INT NOT NULL,
    id_usuario INT NOT NULL,
    fecha_inscripcion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_inscripcion_franja_usuario
        UNIQUE (id_franja, id_usuario),

    CONSTRAINT fk_inscripcion_franja
        FOREIGN KEY (id_franja)
        REFERENCES franja_voluntariado(id_franja)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_inscripcion_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB;


-- ============================================================
-- 10. CUOTAS SOCIALES
-- ============================================================

CREATE TABLE cuota_social (
    id_cuota INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,

    periodo DATE NOT NULL,
    monto DECIMAL(10,2) NOT NULL,

    estado ENUM(
        'PENDIENTE',
        'PAGADA',
        'VENCIDA'
    ) NOT NULL DEFAULT 'PENDIENTE',

    fecha_pago DATETIME NULL,

    CONSTRAINT uq_cuota_usuario_periodo
        UNIQUE (id_usuario, periodo),

    CONSTRAINT fk_cuota_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT chk_cuota_monto
        CHECK (monto >= 0)
) ENGINE=InnoDB;


-- ============================================================
-- 11. DONACIONES
-- ============================================================

CREATE TABLE donacion (
    id_donacion INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,

    monto DECIMAL(10,2) NOT NULL,
    metodo_pago VARCHAR(50) NOT NULL,
    estado ENUM(
        'PENDIENTE',
        'APROBADA',
        'RECHAZADA'
    ) NOT NULL DEFAULT 'PENDIENTE',

    fecha_donacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_donacion_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT chk_donacion_monto
        CHECK (monto > 0)
) ENGINE=InnoDB;


-- ============================================================
-- 12. TRANSPARENCIA
-- ============================================================

CREATE TABLE documento_transparencia (
    id_documento INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario INT NOT NULL,

    titulo VARCHAR(200) NOT NULL,
    periodo DATE NOT NULL,
    archivo_url VARCHAR(500) NOT NULL,
    fecha_publicacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_transparencia_periodo
        UNIQUE (periodo),

    CONSTRAINT fk_transparencia_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE=InnoDB;


-- ============================================================
-- 13. ENCUESTAS
-- ============================================================

CREATE TABLE encuesta (
    id_encuesta INT AUTO_INCREMENT PRIMARY KEY,
    id_creador INT NOT NULL,

    pregunta TEXT NOT NULL,
    fecha_inicio DATETIME NOT NULL,
    fecha_fin DATETIME NOT NULL,
    activa BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_encuesta_creador
        FOREIGN KEY (id_creador)
        REFERENCES usuario(id_usuario)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    CONSTRAINT chk_encuesta_fechas
        CHECK (fecha_fin > fecha_inicio),

    CONSTRAINT chk_encuesta_pregunta
        CHECK (CHAR_LENGTH(TRIM(pregunta)) > 0)
) ENGINE=InnoDB;


CREATE TABLE opcion_encuesta (
    id_opcion INT AUTO_INCREMENT PRIMARY KEY,
    id_encuesta INT NOT NULL,

    texto VARCHAR(200) NOT NULL,

    CONSTRAINT fk_opcion_encuesta
        FOREIGN KEY (id_encuesta)
        REFERENCES encuesta(id_encuesta)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT uq_opcion_encuesta
        UNIQUE (id_encuesta, texto)
) ENGINE=InnoDB;

CREATE TABLE voto (
    id_voto INT AUTO_INCREMENT PRIMARY KEY,
    id_opcion INT NOT NULL,
    id_usuario INT NOT NULL,

    fecha_voto DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_voto_usuario_encuesta
        UNIQUE (id_usuario, id_opcion),

    CONSTRAINT fk_voto_opcion
        FOREIGN KEY (id_opcion)
        REFERENCES opcion_encuesta(id_opcion)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_voto_usuario
        FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB;

-- ============================================================
-- 14. ÍNDICES PARA MEJORAR CONSULTAS
-- ============================================================

CREATE INDEX idx_usuario_email
    ON usuario(email);

CREATE INDEX idx_producto_categoria
    ON producto(id_categoria);

CREATE INDEX idx_variante_producto
    ON variante_producto(id_producto);

CREATE INDEX idx_carrito_usuario_estado
    ON carrito(id_usuario, estado);

CREATE INDEX idx_pedido_usuario
    ON pedido(id_usuario);

CREATE INDEX idx_pedido_estado
    ON pedido(estado);

CREATE INDEX idx_detalle_pedido_pedido
    ON detalle_pedido(id_pedido);

CREATE INDEX idx_pago_pedido
    ON pago(id_pedido);

CREATE INDEX idx_publicacion_fecha
    ON publicacion(fecha_publicacion);

CREATE INDEX idx_evento_fecha
    ON evento(fecha_inicio, fecha_fin);

CREATE INDEX idx_evento_espacio_fecha
    ON evento(id_espacio, fecha_inicio, fecha_fin);

CREATE INDEX idx_cuota_usuario
    ON cuota_social(id_usuario);

CREATE INDEX idx_donacion_usuario
    ON donacion(id_usuario);

CREATE INDEX idx_voto_usuario
    ON voto(id_usuario);


-- ============================================================
-- 15. DATOS INICIALES DE ROLES
-- ============================================================

INSERT INTO rol (nombre) VALUES
('PADRE'),
('ALUMNO'),
('DOCENTE'),
('COOPERADORA'),
('STAFF'),
('ADMIN');


-- ============================================================
-- FIN DEL MODELO
-- ============================================================
