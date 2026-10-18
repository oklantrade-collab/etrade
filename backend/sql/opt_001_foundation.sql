-- ============================================================
-- eTrader APEX Options - migracion opt_001 (aditiva y reversible)
-- Rollback: ver bloque al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_settings (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL,
    updated_by  TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS opt_settings_audit (
    id             BIGSERIAL PRIMARY KEY,
    settings_version INT NOT NULL,
    key            TEXT NOT NULL,
    old_value      JSONB,
    new_value      JSONB,
    changed_by     TEXT,
    changed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS opt_jobs (
    id          BIGSERIAL PRIMARY KEY,
    type        TEXT NOT NULL CHECK (type IN ('scan','g1_probe','chain_sync','snapshot')),
    params      JSONB NOT NULL DEFAULT '{}'::jsonb,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','done','error','cancelled')),
    result      JSONB,
    error       TEXT,
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_opt_jobs_status ON opt_jobs (status, created_at);

CREATE TABLE IF NOT EXISTS opt_worker_heartbeat (
    worker      TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    data_state  TEXT,
    detail      JSONB,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Resultado por sesion del Sprint 0.5 (Gate G1)
CREATE TABLE IF NOT EXISTS opt_g1_sessions (
    id                    BIGSERIAL PRIMARY KEY,
    session_date          DATE NOT NULL,
    symbols_evaluated     INT NOT NULL DEFAULT 0,
    optionable_count      INT NOT NULL DEFAULT 0,
    viable_candidates     INT NOT NULL DEFAULT 0,
    market_data_type      TEXT,
    details               JSONB,
    session_pass          BOOLEAN,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_date)
);

-- RLS: sin politicas = solo service_role (backend). Frontend usa la API.
ALTER TABLE opt_settings          ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_settings_audit    ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_jobs              ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_worker_heartbeat  ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_g1_sessions       ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- DROP TABLE IF EXISTS opt_g1_sessions, opt_worker_heartbeat, opt_jobs, opt_settings_audit, opt_settings;
