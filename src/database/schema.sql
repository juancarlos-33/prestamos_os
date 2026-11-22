-- Esquema Relacional de Base de Datos para Sistema de Gestión de Préstamos
-- Motor: SQLite3 con soporte de Transacciones ACID y claves foráneas activas

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    descripcion TEXT
);

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rol_id INTEGER NOT NULL,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nombre_completo TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (rol_id) REFERENCES roles(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_documento TEXT NOT NULL,
    numero_documento TEXT NOT NULL UNIQUE,
    nombres TEXT NOT NULL,
    apellidos TEXT NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    telefono TEXT NOT NULL,
    correo TEXT NOT NULL,
    direccion TEXT NOT NULL,
    ocupacion TEXT,
    ingresos_mensuales NUMERIC(14, 2) NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_clientes_documento ON clientes(numero_documento);
CREATE INDEX IF NOT EXISTS idx_clientes_nombres ON clientes(nombres, apellidos);

CREATE TABLE IF NOT EXISTS prestamos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL,
    monto_solicitado NUMERIC(14, 2) NOT NULL,
    tasa_interes NUMERIC(6, 2) NOT NULL,
    tipo_tasa TEXT NOT NULL CHECK(tipo_tasa IN ('MENSUAL', 'ANUAL')),
    plazo_cuotas INTEGER NOT NULL,
    periodicidad TEXT NOT NULL CHECK(periodicidad IN ('SEMANAL', 'QUINCENAL', 'MENSUAL')),
    sistema_amortizacion TEXT NOT NULL CHECK(sistema_amortizacion IN ('FRANCES', 'ALEMAN', 'SIMPLE')),
    seguro_comision NUMERIC(14, 2) DEFAULT 0.00,
    tipo_seguro TEXT NOT NULL CHECK(tipo_seguro IN ('FIJO', 'PORCENTAJE')),
    fecha_desembolso DATE NOT NULL,
    estado TEXT NOT NULL CHECK(estado IN ('SIMULADO', 'ACTIVO', 'EN_MORA', 'CANCELADO', 'CASTIGADO')),
    saldo_capital_actual NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE RESTRICT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_prestamos_cliente ON prestamos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_prestamos_estado ON prestamos(estado);

CREATE TABLE IF NOT EXISTS cuotas_amortizacion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prestamo_id INTEGER NOT NULL,
    numero_cuota INTEGER NOT NULL,
    fecha_vencimiento DATE NOT NULL,
    abono_capital NUMERIC(14, 2) NOT NULL,
    interes_corriente NUMERIC(14, 2) NOT NULL,
    cargo_adicional NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    cuota_total NUMERIC(14, 2) NOT NULL,
    saldo_restante NUMERIC(14, 2) NOT NULL,
    estado TEXT NOT NULL CHECK(estado IN ('PENDIENTE', 'PAGADA', 'EN_MORA')),
    saldo_pendiente_cuota NUMERIC(14, 2) NOT NULL,
    FOREIGN KEY (prestamo_id) REFERENCES prestamos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cuotas_prestamo ON cuotas_amortizacion(prestamo_id);
CREATE INDEX IF NOT EXISTS idx_cuotas_vencimiento ON cuotas_amortizacion(fecha_vencimiento, estado);

CREATE TABLE IF NOT EXISTS pagos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prestamo_id INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL,
    fecha_pago TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    monto_recibido NUMERIC(14, 2) NOT NULL,
    metodo_pago TEXT NOT NULL CHECK(metodo_pago IN ('EFECTIVO', 'TRANSFERENCIA', 'CHEQUE')),
    numero_recibo TEXT NOT NULL UNIQUE,
    aplicado_mora NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    aplicado_interes NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    aplicado_capital NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    ruta_pdf_comprobante TEXT,
    FOREIGN KEY (prestamo_id) REFERENCES prestamos(id) ON DELETE RESTRICT,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS detalle_pago_cuota (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pago_id INTEGER NOT NULL,
    cuota_id INTEGER NOT NULL,
    monto_aplicado NUMERIC(14, 2) NOT NULL,
    FOREIGN KEY (pago_id) REFERENCES pagos(id) ON DELETE CASCADE,
    FOREIGN KEY (cuota_id) REFERENCES cuotas_amortizacion(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS feriados (
    fecha DATE PRIMARY KEY,
    descripcion TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS log_actividad (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    nivel TEXT NOT NULL CHECK(nivel IN ('INFO', 'WARNING', 'ERROR')),
    modulo TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
);
