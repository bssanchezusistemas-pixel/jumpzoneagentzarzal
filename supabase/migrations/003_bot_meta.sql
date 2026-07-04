-- Jumping Fit — tablas bot WhatsApp (memoria IA + sesiones reserva WA)
-- Ejecutar después de 001 y 002

CREATE TABLE IF NOT EXISTS mensajes (
    id SERIAL PRIMARY KEY,
    telefono VARCHAR(50) NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mensajes_telefono ON mensajes(telefono);
CREATE INDEX IF NOT EXISTS idx_mensajes_telefono_ts ON mensajes(telefono, timestamp DESC);

CREATE TABLE IF NOT EXISTS wa_sessions (
    telefono VARCHAR(50) PRIMARY KEY,
    etapa VARCHAR(30) DEFAULT 'idle',
    datos TEXT DEFAULT '{}',
    actualizado TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wa_sessions_actualizado ON wa_sessions(actualizado);
