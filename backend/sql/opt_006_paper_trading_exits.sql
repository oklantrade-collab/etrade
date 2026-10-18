-- ============================================================
-- eTrader APEX Options - migracion opt_006 (Sprint 6: Paper Trading y Salidas)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_paper_trades (
    id                      BIGSERIAL PRIMARY KEY,
    candidate_id            BIGINT REFERENCES opt_candidates(id) ON DELETE SET NULL,
    underlying_id           BIGINT NOT NULL REFERENCES opt_underlyings(id) ON DELETE CASCADE,
    symbol                  TEXT NOT NULL,
    strategy_type           TEXT NOT NULL CHECK (strategy_type IN ('long_call','long_put','bull_call_spread','bear_put_spread')),
    direction               TEXT NOT NULL CHECK (direction IN ('bullish','bearish')),
    status                  TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','cancelled')),
    qty                     INT NOT NULL DEFAULT 1 CHECK (qty >= 1),
    expiry                  DATE NOT NULL,
    entry_time              TIMESTAMPTZ NOT NULL DEFAULT now(),
    entry_debit             NUMERIC NOT NULL,            -- por accion
    entry_fills             JSONB NOT NULL DEFAULT '[]'::jsonb,
    entry_costs             NUMERIC NOT NULL DEFAULT 0,  -- comisiones totales USD
    entry_total_invested    NUMERIC NOT NULL,            -- debit * 100 * qty + costs
    max_loss_total          NUMERIC NOT NULL,
    max_profit_total        NUMERIC,                     -- NULL = ilimitado
    breakeven               NUMERIC,
    exit_time               TIMESTAMPTZ,
    exit_credit             NUMERIC,
    exit_fills              JSONB NOT NULL DEFAULT '[]'::jsonb,
    exit_costs              NUMERIC NOT NULL DEFAULT 0,
    exit_total_recovered    NUMERIC,
    realized_pnl            NUMERIC,
    unrealized_pnl          NUMERIC NOT NULL DEFAULT 0,
    last_mark_price         NUMERIC,
    last_mark_at            TIMESTAMPTZ,
    exit_reason             TEXT CHECK (exit_reason IS NULL OR exit_reason IN ('take_profit','stop_loss','forced_close_time','signal_invalidation','bad_data_close','manual_simulated')),
    exit_plan               JSONB NOT NULL DEFAULT '{}'::jsonb,
    aduana_decision_id      BIGINT REFERENCES opt_aduana_decisions(id) ON DELETE SET NULL,
    model_version           TEXT NOT NULL,
    settings_version        INT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_paper_trades_status ON opt_paper_trades (status, entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_opt_paper_trades_symbol ON opt_paper_trades (symbol, status);

-- Vista de compatibilidad para opt_positions
CREATE OR REPLACE VIEW opt_positions AS SELECT * FROM opt_paper_trades;

CREATE TABLE IF NOT EXISTS opt_risk_events (
    id                      BIGSERIAL PRIMARY KEY,
    paper_trade_id          BIGINT NOT NULL REFERENCES opt_paper_trades(id) ON DELETE CASCADE,
    event_type              TEXT NOT NULL CHECK (event_type IN ('bad_data','stale_quote','signal_flip','time_warning','stop_approaching','early_close_warning','margin_warning','forced_close')),
    details                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_risk_events_trade ON opt_risk_events (paper_trade_id, created_at DESC);

-- Actualizar constraint de opt_jobs para incluir tareas de salida y paper
ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check;
ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates','portfolio_select','exit_check'));

ALTER TABLE opt_paper_trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_risk_events  ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- DROP TABLE IF EXISTS opt_risk_events CASCADE;
-- DROP VIEW IF EXISTS opt_positions CASCADE;
-- DROP TABLE IF EXISTS opt_paper_trades CASCADE;
-- ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check;
-- ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates','portfolio_select'));
