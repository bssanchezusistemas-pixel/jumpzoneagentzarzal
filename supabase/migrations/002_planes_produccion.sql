-- Jump Zone producción — planes y paquetes
-- Ejecutar en Supabase SQL Editor

CREATE TABLE IF NOT EXISTS plans (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(30) UNIQUE NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    clases_incluidas INTEGER NOT NULL,
    vigencia_dias INTEGER DEFAULT 30,
    precio NUMERIC(10, 2) DEFAULT 0,
    descripcion TEXT DEFAULT '',
    activo INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS client_packages (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES clients(id),
    plan_id INTEGER NOT NULL REFERENCES plans(id),
    clases_totales INTEGER NOT NULL,
    clases_restantes INTEGER NOT NULL,
    reprogramaciones_usadas INTEGER DEFAULT 0,
    estado VARCHAR(30) DEFAULT 'pendiente_pago',
    pago_metodo VARCHAR(30) DEFAULT '',
    pago_estado VARCHAR(30) DEFAULT 'pendiente',
    total_pagar NUMERIC(10, 2) DEFAULT 0,
    creado TIMESTAMPTZ DEFAULT NOW(),
    vence DATE
);

ALTER TABLE bookings ADD COLUMN IF NOT EXISTS package_id INTEGER REFERENCES client_packages(id);

CREATE TABLE IF NOT EXISTS package_sessions (
    id SERIAL PRIMARY KEY,
    package_id INTEGER NOT NULL REFERENCES client_packages(id),
    slot_id INTEGER NOT NULL REFERENCES slots(id),
    booking_id INTEGER REFERENCES bookings(id),
    estado VARCHAR(30) DEFAULT 'programada'
);

CREATE TABLE IF NOT EXISTS payment_receipts (
    id SERIAL PRIMARY KEY,
    package_id INTEGER REFERENCES client_packages(id),
    client_id INTEGER NOT NULL REFERENCES clients(id),
    imagen_url TEXT DEFAULT '',
    monto_detectado NUMERIC(10, 2),
    confianza REAL,
    ia_notas TEXT DEFAULT '',
    estado VARCHAR(30) DEFAULT 'pendiente',
    creado TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO plans (codigo, nombre, clases_incluidas, vigencia_dias, precio, descripcion) VALUES
    ('dia', 'Día suelto', 1, 7, 0, '1 clase'),
    ('semana', 'Plan semana', 3, 14, 90000, '3 clases a elegir'),
    ('quincena', 'Plan quincena', 6, 21, 160000, '6 clases en 2 semanas'),
    ('mes', 'Plan mes', 12, 45, 280000, '12 clases a programar')
ON CONFLICT (codigo) DO NOTHING;
