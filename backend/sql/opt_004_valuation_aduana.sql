-- ============================================================
-- eTrader APEX Options - migracion opt_004 (Sprint 4: simulaciones y decisiones ADUANA)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_simulations (
    id                      BIGSERIAL PRIMARY KEY,
    candidate_id            BIGINT NOT NULL REFERENCES opt_candidates(id) ON DELETE CASCADE,
    scenario_config         JSONB NOT NULL,      -- horizonte, alpha, k, IV de referencia, supuestos
    scenario_results        JSONB NOT NULL,      -- cuadricula movimiento x IV (normal y adverso)
    cost_assumptions        JSONB NOT NULL,
    pricing_model_version   TEXT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_simulations_candidate ON opt_simulations (candidate_id, created_at DESC);

CREATE TABLE IF NOT EXISTS opt_aduana_decisions (
    id              BIGSERIAL PRIMARY KEY,
    candidate_id    BIGINT REFERENCES opt_candidates(id) ON DELETE SET NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('entry','exit','valuation')),
    approved        BOOLEAN NOT NULL,
    rules           JSONB NOT NULL,
    warnings        JSONB NOT NULL DEFAULT '[]'::jsonb,
    settings_version INT NOT NULL DEFAULT 0,
    model_version   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_aduana_candidate ON opt_aduana_decisions (candidate_id, created_at DESC);

-- Reutiliza opt_candidates: las columnas ev_*, pop_*, alpha_used ya existen (Sprint 3). Aqui solo se agrega:
ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS expected_move NUMERIC;
ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS ev_view_adverse NUMERIC;
ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS ev_ratio NUMERIC;
ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS valuation_warnings JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE opt_simulations      ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_aduana_decisions ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- ALTER TABLE opt_candidates DROP COLUMN IF EXISTS valuation_warnings, DROP COLUMN IF EXISTS ev_ratio,
--   DROP COLUMN IF EXISTS ev_view_adverse, DROP COLUMN IF EXISTS expected_move;
-- DROP TABLE IF EXISTS opt_aduana_decisions, opt_simulations;
