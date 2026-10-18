-- ============================================================
-- eTrader APEX Options - migracion opt_007 (Sprint 7: Performance y Evaluacion Gate G3)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_g3_evaluations (
    id                      BIGSERIAL PRIMARY KEY,
    evaluation_date         DATE NOT NULL DEFAULT CURRENT_DATE,
    verdict                 TEXT NOT NULL CHECK (verdict IN ('GO', 'NO-GO', 'PENDING')),
    total_trades            INT NOT NULL DEFAULT 0,
    weeks_in_shadow         NUMERIC NOT NULL DEFAULT 0,
    expectancy_usd          NUMERIC NOT NULL DEFAULT 0,
    win_rate_pct            NUMERIC NOT NULL DEFAULT 0,
    max_drawdown_usd        NUMERIC NOT NULL DEFAULT 0,
    calibration_error_pts   NUMERIC NOT NULL DEFAULT 0,
    criteria                JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_version           TEXT NOT NULL,
    settings_version        INT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_g3_eval_date ON opt_g3_evaluations (evaluation_date DESC, created_at DESC);

ALTER TABLE opt_g3_evaluations ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- DROP TABLE IF EXISTS opt_g3_evaluations;
