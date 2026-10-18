-- ============================================================
-- eTrader APEX Options - migracion opt_003 (Sprint 3: candidatas)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_candidates (
    id                   BIGSERIAL PRIMARY KEY,
    underlying_id        BIGINT NOT NULL REFERENCES opt_underlyings(id) ON DELETE CASCADE,
    strategy_type        TEXT NOT NULL CHECK (strategy_type IN ('long_call','long_put','bull_call_spread','bear_put_spread')),
    direction            TEXT NOT NULL CHECK (direction IN ('bullish','bearish')),
    direction_source     TEXT NOT NULL DEFAULT 'unverified',   -- 'apex' | 'unverified'
    expiry               DATE NOT NULL,
    legs                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    qty                  INT CHECK (qty IS NULL OR qty >= 1),
    entry_debit          NUMERIC,            -- por accion, ejecutable
    mid_debit            NUMERIC,
    max_loss_contract    NUMERIC,            -- USD por contrato, con costes
    max_loss_total       NUMERIC,
    max_profit_contract  NUMERIC,            -- NULL = ilimitado teorico
    breakeven            NUMERIC,
    costs_contract       NUMERIC,
    exec_overcost_pct    NUMERIC,
    exit_plan            JSONB,
    -- Se rellenan en Sprints 4-5 (NULL hasta entonces, nunca 0)
    ev_neutral_net       NUMERIC,
    ev_view_net          NUMERIC,
    pop_neutral          NUMERIC,
    pop_view             NUMERIC,
    alpha_used           NUMERIC,
    score                NUMERIC,
    score_breakdown      JSONB,
    eligibility_status   TEXT NOT NULL DEFAULT 'pending'
                         CHECK (eligibility_status IN ('pending','rejected','eligible','selected','expired')),
    rejection_reasons    JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings             JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_quality         JSONB,
    model_version        TEXT NOT NULL,
    settings_version     INT NOT NULL DEFAULT 0,
    snapshot_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_candidates_created_score ON opt_candidates (created_at DESC, score DESC);
CREATE INDEX IF NOT EXISTS idx_opt_candidates_underlying ON opt_candidates (underlying_id, eligibility_status);

ALTER TABLE opt_candidates ENABLE ROW LEVEL SECURITY;


-- Nuevo tipo de job para el worker
ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check;
ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates'));
-- ROLLBACK:
-- DROP TABLE IF EXISTS opt_candidates;
-- ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check; ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot'));

