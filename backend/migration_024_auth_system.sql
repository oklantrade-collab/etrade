-- ==========================================================
-- MIGRATION 024 — eTrade Auth & Admin System
-- ==========================================================

-- 1. Tabla: roles
CREATE TABLE IF NOT EXISTS roles (
    id                  BIGSERIAL PRIMARY KEY,
    nombre              VARCHAR(50) UNIQUE NOT NULL,
    codigo_registro     VARCHAR(100) UNIQUE NOT NULL,
    descripcion         TEXT,
    activo              BOOLEAN DEFAULT true,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Tabla: usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre              VARCHAR(100) NOT NULL,
    correo              VARCHAR(100) UNIQUE NOT NULL,
    password            VARCHAR(255) NOT NULL,
    rol_id              BIGINT REFERENCES roles(id) ON DELETE SET NULL,
    verificado          BOOLEAN DEFAULT false,
    token_verificacion  VARCHAR(255),
    token_expiracion    TIMESTAMPTZ,
    token_reset_pass    VARCHAR(255),
    token_reset_exp     TIMESTAMPTZ,
    fecha_registro      TIMESTAMPTZ DEFAULT NOW(),
    activo              BOOLEAN DEFAULT true,
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Seed inicial de roles
INSERT INTO roles (nombre, codigo_registro, descripcion)
VALUES 
('CEO', 'etrade369', 'Acceso total al sistema y gestión de usuarios.'),
('Visita', 'etrade123', 'Acceso limitado de solo lectura a la plataforma.')
ON CONFLICT (nombre) DO NOTHING;

-- 4. Índices para búsqueda rápida
CREATE INDEX IF NOT EXISTS idx_usuarios_correo ON usuarios(correo);
CREATE INDEX IF NOT EXISTS idx_usuarios_rol ON usuarios(rol_id);
CREATE INDEX IF NOT EXISTS idx_roles_codigo ON roles(codigo_registro);
