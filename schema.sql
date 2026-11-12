-- =====================================================================
--  El Fogón Bumangués - Esquema de la base de datos (PostgreSQL)
--  Corresponde 1 a 1 con el modelo relacional del documento.
--
--  · Montos en pesos colombianos, como números enteros (sin decimales).
--  · Fechas como texto AAAA-MM-DD y horas como texto HH:MM.
--  · Los campos Sí/No se guardan como 0 / 1 (INTEGER), igual que en el modelo.
--  · Se puede ejecutar varias veces: solo crea lo que todavía no existe.
-- =====================================================================

-- ---------------------------------------------------------------------
-- CLIENTE: clientes que piden ser identificados. Existe un cliente
-- genérico "Consumidor final" que se usa por defecto.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS CLIENTE (
    id_cliente            INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    numero_identificacion TEXT    NOT NULL UNIQUE,
    nombre                TEXT    NOT NULL
);

-- ---------------------------------------------------------------------
-- USUARIO: personas que usan el sistema. La contraseña se guarda
-- cifrada con hash (nunca en texto plano).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS USUARIO (
    id_usuario  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre      TEXT    NOT NULL,
    usuario     TEXT    NOT NULL UNIQUE,
    contrasena  TEXT    NOT NULL,
    rol         TEXT    NOT NULL CHECK (rol IN ('administrador', 'cajero'))
);

-- ---------------------------------------------------------------------
-- PRODUCTO: catálogo de platos, bebidas y otros (p. ej. empaque).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PRODUCTO (
    id_producto       INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre            TEXT    NOT NULL,
    categoria         TEXT    NOT NULL CHECK (categoria IN ('almuerzo', 'bebida', 'otro')),
    precio_unitario   INTEGER NOT NULL CHECK (precio_unitario >= 0),
    incluye_principio INTEGER NOT NULL DEFAULT 0 CHECK (incluye_principio IN (0, 1)),
    activo            INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

-- ---------------------------------------------------------------------
-- PRINCIPIO: acompañamientos del día (frijol, guiso, etc.).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PRINCIPIO (
    id_principio INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre       TEXT    NOT NULL,
    activo       INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1))
);

-- ---------------------------------------------------------------------
-- METODO_PAGO: efectivo o transferencia.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS METODO_PAGO (
    id_metodo INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre    TEXT    NOT NULL UNIQUE CHECK (nombre IN ('efectivo', 'transferencia'))
);

-- ---------------------------------------------------------------------
-- CIERRE_CAJA: una jornada de caja (fecha + turno). Solo puede existir
-- un cierre por fecha y turno. Las diferencias NO se guardan: se
-- calculan cada vez que se consultan.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS CIERRE_CAJA (
    id_cierre                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha                      TEXT    NOT NULL CHECK (fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
    turno                      TEXT    NOT NULL CHECK (turno IN ('almuerzo', 'noche')),
    hora_apertura              TEXT    NOT NULL CHECK (hora_apertura ~ '^[0-9]{2}:[0-9]{2}$'),
    base_inicial               INTEGER NOT NULL CHECK (base_inicial >= 0),
    hora_cierre                TEXT             CHECK (hora_cierre ~ '^[0-9]{2}:[0-9]{2}$'),
    efectivo_contado           INTEGER          CHECK (efectivo_contado >= 0),
    transferencias_registradas INTEGER          CHECK (transferencias_registradas >= 0),
    estado                     TEXT    NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto', 'cerrado')),
    id_usuario                 INTEGER NOT NULL REFERENCES USUARIO (id_usuario),
    UNIQUE (fecha, turno)
);

-- ---------------------------------------------------------------------
-- VENTA: encabezado de cada venta. id_venta es el consecutivo.
-- Las ventas nunca se borran: se anulan con un motivo obligatorio.
-- valor_total = suma de (cantidad x precio_unitario) de sus detalles.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS VENTA (
    id_venta         INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fecha            TEXT    NOT NULL CHECK (fecha ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'),
    hora             TEXT    NOT NULL CHECK (hora ~ '^[0-9]{2}:[0-9]{2}$'),
    valor_total      INTEGER NOT NULL CHECK (valor_total > 0),
    estado           TEXT    NOT NULL DEFAULT 'activa' CHECK (estado IN ('activa', 'anulada')),
    motivo_anulacion TEXT,
    id_cliente       INTEGER REFERENCES CLIENTE (id_cliente),
    id_usuario       INTEGER NOT NULL REFERENCES USUARIO (id_usuario),
    id_cierre        INTEGER NOT NULL REFERENCES CIERRE_CAJA (id_cierre),
    -- Una venta anulada siempre debe tener motivo.
    CHECK (estado = 'activa' OR (motivo_anulacion IS NOT NULL AND trim(motivo_anulacion) <> ''))
);

-- ---------------------------------------------------------------------
-- DETALLE_VENTA: cada línea de la venta. Guarda el precio del producto
-- en el momento de la venta. El subtotal NO se guarda: se calcula.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS DETALLE_VENTA (
    id_detalle      INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_venta        INTEGER NOT NULL REFERENCES VENTA (id_venta),
    id_producto     INTEGER NOT NULL REFERENCES PRODUCTO (id_producto),
    id_principio    INTEGER REFERENCES PRINCIPIO (id_principio),
    cantidad        INTEGER NOT NULL CHECK (cantidad > 0),
    precio_unitario INTEGER NOT NULL CHECK (precio_unitario >= 0)
);

-- ---------------------------------------------------------------------
-- PAGO: uno o varios pagos por venta. Su suma debe ser igual a
-- valor_total (esta regla la valida la aplicación antes de guardar).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PAGO (
    id_pago   INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_venta  INTEGER NOT NULL REFERENCES VENTA (id_venta),
    id_metodo INTEGER NOT NULL REFERENCES METODO_PAGO (id_metodo),
    valor     INTEGER NOT NULL CHECK (valor > 0)
);

-- Índices para que las consultas de ventas, cierres y reportes sean rápidas.
CREATE INDEX IF NOT EXISTS idx_venta_cierre  ON VENTA (id_cierre);
CREATE INDEX IF NOT EXISTS idx_venta_fecha   ON VENTA (fecha);
CREATE INDEX IF NOT EXISTS idx_detalle_venta ON DETALLE_VENTA (id_venta);
CREATE INDEX IF NOT EXISTS idx_pago_venta    ON PAGO (id_venta);
