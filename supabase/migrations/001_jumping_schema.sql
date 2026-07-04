-- Jump Zone — Schema PostgreSQL (Supabase)
-- Ejecutar en SQL Editor o vía Supabase CLI

CREATE TABLE IF NOT EXISTS class_types (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    duracion_minutos INTEGER DEFAULT 60,
    precio NUMERIC(10, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS slots (
    id SERIAL PRIMARY KEY,
    class_type_id INTEGER REFERENCES class_types(id),
    fecha DATE NOT NULL,
    hora_inicio TIME NOT NULL,
    capacity_max INTEGER DEFAULT 15,
    capacity_booked INTEGER DEFAULT 0,
    estado VARCHAR(20) DEFAULT 'activo'
);

CREATE INDEX IF NOT EXISTS idx_slots_fecha ON slots(fecha);

CREATE TABLE IF NOT EXISTS clients (
    id SERIAL PRIMARY KEY,
    telefono VARCHAR(50) UNIQUE NOT NULL,
    nombre VARCHAR(100) DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_clients_telefono ON clients(telefono);

CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    slot_id INTEGER NOT NULL REFERENCES slots(id),
    client_id INTEGER NOT NULL REFERENCES clients(id),
    personas INTEGER DEFAULT 1,
    estado VARCHAR(30) DEFAULT 'pendiente_pago',
    pago_estado VARCHAR(30) DEFAULT 'pendiente',
    notas TEXT DEFAULT '',
    creado TIMESTAMPTZ DEFAULT NOW(),
    reprogramado_de INTEGER,
    recordatorio_enviado INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_bookings_slot ON bookings(slot_id);
CREATE INDEX IF NOT EXISTS idx_bookings_client ON bookings(client_id);

-- Datos iniciales (opcional)
INSERT INTO class_types (nombre, duracion_minutos, precio) VALUES
    ('Jump Básico', 60, 35000),
    ('Jump Intermedio', 60, 40000),
    ('Jump Avanzado', 60, 45000),
    ('Open Jump', 60, 30000)
ON CONFLICT DO NOTHING;
