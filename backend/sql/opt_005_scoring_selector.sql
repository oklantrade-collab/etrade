-- ============================================================
-- eTrader APEX Options - migracion opt_005 (Sprint 5: Scoring y Selector de Cartera)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_selections (
    id                      BIGSERIAL PRIMARY KEY,
    session_date            DATE NOT NULL DEFAULT CURRENT_DATE,
    selected_candidate_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
    selections_detail       JSONB NOT NULL DEFAULT '[]'::jsonb,
    skipped_detail          JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_risk_allocated    NUMERIC NOT NULL DEFAULT 0,
    remaining_budget        NUMERIC NOT NULL DEFAULT 0,
    portfolio_state         JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_version           TEXT NOT NULL,
    settings_version        INT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_selections_session ON opt_selections (session_date DESC, created_at DESC);

ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS rank_global INT;
ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS rank_strategy INT;

ALTER TABLE opt_selections ENABLE ROW LEVEL SECURITY;

ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check;
ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates','portfolio_select'));

-- ROLLBACK:
-- ALTER TABLE opt_candidates DROP COLUMN IF EXISTS rank_strategy, DROP COLUMN IF EXISTS rank_global;
-- DROP TABLE IF EXISTS opt_selections;
-- ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check; ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates'));

