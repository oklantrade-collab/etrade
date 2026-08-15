-- migration_034_rebote_aduana.sql
-- Schema additions for the REBOTE / ADUANA entry-management subsystem.

-- 1. rebote_scores_log — every evaluation by ReboteEngine
CREATE TABLE IF NOT EXISTS rebote_scores_log (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    direction       TEXT NOT NULL,           -- 'long' | 'short'
    score_raw       NUMERIC(8,2),
    score_final     NUMERIC(8,2),
    decision        TEXT NOT NULL DEFAULT 'SKIP',
    regime_adx      TEXT,
    regime_local    TEXT,
    contra_trend    BOOLEAN DEFAULT FALSE,
    contra_trend_confirmed BOOLEAN DEFAULT FALSE,
    volume_confirmed BOOLEAN DEFAULT FALSE,
    fib_zone        INT,
    signals         JSONB,
    detail          JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- indices
CREATE INDEX IF NOT EXISTS idx_rebote_log_symbol ON rebote_scores_log(symbol);
CREATE INDEX IF NOT EXISTS idx_rebote_log_created ON rebote_scores_log(created_at);
CREATE INDEX IF NOT EXISTS idx_rebote_log_decision ON rebote_scores_log(decision);

-- 2. aduana_decisions_log
CREATE TABLE IF NOT EXISTS aduana_decisions_log (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    order_type      TEXT NOT NULL,
    strategy_source TEXT,
    approved        BOOLEAN NOT NULL,
    rule_triggered  TEXT,
    step            INT,
    reason          TEXT,
    detail          JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_aduana_log_symbol ON aduana_decisions_log(symbol);
CREATE INDEX IF NOT EXISTS idx_aduana_log_created ON aduana_decisions_log(created_at);
CREATE INDEX IF NOT EXISTS idx_aduana_log_approved ON aduana_decisions_log(approved);

-- 3. system_config entries for REBOTE/ADUANA
INSERT INTO system_config (key, value, description) VALUES
    ('rebote_enabled', 'true', 'Enable REBOTE entry engine'),
    ('rebote_score_min_entry', '50', 'Minimum score for first REBOTE entry'),
    ('rebote_score_min_additional', '70', 'Minimum score for additional REBOTE entry'),
    ('rebote_adx_range_multiplier', '1.2', 'ADX range multiplier for REBOTE'),
    ('rebote_adx_trend_multiplier', '0.5', 'ADX strong trend multiplier for REBOTE'),
    ('aduana_enabled', 'true', 'Enable ADUANA order validator'),
    ('aduana_impulse_atr_ratio', '1.8', 'Impulse candle ATR ratio threshold for ADUANA')
ON CONFLICT (key) DO NOTHING;
