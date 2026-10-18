-- ============================================================
-- eTrader APEX Options & Universe - migracion opt_009
-- Tablas del Universe Pool, eventos de catalizadores y estado
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS universe_pool (
    trade_date          DATE NOT NULL,
    symbol              TEXT NOT NULL,
    source              TEXT NOT NULL,            -- 'ib_gain' | 'ib_lose' | 'ib_gap_up' | 'ib_gap_down' | 'ib_volume' | 'yahoo' | 'seed'
    pool_type           TEXT,
    price               NUMERIC,
    prev_close          NUMERIC,
    open_price          NUMERIC,
    change_pct          NUMERIC,
    gap_pct             NUMERIC,
    avg_volume          BIGINT,
    dollar_volume       NUMERIC,
    market_cap          NUMERIC,
    stocks_eligible     BOOLEAN NOT NULL DEFAULT FALSE,
    options_eligible    BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_universe_pool_date ON universe_pool (trade_date);
CREATE INDEX IF NOT EXISTS idx_universe_pool_options ON universe_pool (trade_date, options_eligible);

CREATE TABLE IF NOT EXISTS universe_catalyst_events (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    catalyst            TEXT NOT NULL CHECK (catalyst IN ('gap_go','sipv_basis_1h','adx_di_5m','rebote_15m')),
    direction           TEXT NOT NULL CHECK (direction IN ('bullish','bearish')),
    strength            NUMERIC,
    timeframe           TEXT,
    bar_time            TIMESTAMPTZ NOT NULL,
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ NOT NULL,
    data_state          TEXT,
    meta                JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (symbol, catalyst, direction, bar_time)
);
CREATE INDEX IF NOT EXISTS idx_catalyst_events_active ON universe_catalyst_events (symbol, expires_at);

CREATE TABLE IF NOT EXISTS universe_catalyst_state (
    symbol              TEXT PRIMARY KEY,
    direction           TEXT CHECK (direction IN ('bullish','bearish','neutral')),
    catalyst_score      NUMERIC,
    rule_applied        TEXT,
    active_catalysts    TEXT[] NOT NULL DEFAULT '{}',
    components          JSONB NOT NULL DEFAULT '{}'::jsonb,
    reasons             JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Columnas adicionales para opt_underlyings
ALTER TABLE opt_underlyings ADD COLUMN IF NOT EXISTS direction_source     TEXT;
ALTER TABLE opt_underlyings ADD COLUMN IF NOT EXISTS catalyst_score       NUMERIC;
ALTER TABLE opt_underlyings ADD COLUMN IF NOT EXISTS catalyst_meta        JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE opt_underlyings ADD COLUMN IF NOT EXISTS catalyst_updated_at  TIMESTAMPTZ;
ALTER TABLE opt_underlyings ADD COLUMN IF NOT EXISTS optionable_checked_at TIMESTAMPTZ;

-- Ampliar tipos de job en opt_jobs para sincronizacion de catalizadores
ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check;
ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check 
    CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates','portfolio_select','catalyst_sync'));

-- RLS
ALTER TABLE universe_pool             ENABLE ROW LEVEL SECURITY;
ALTER TABLE universe_catalyst_events  ENABLE ROW LEVEL SECURITY;
ALTER TABLE universe_catalyst_state   ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- DROP TABLE IF EXISTS universe_catalyst_state, universe_catalyst_events, universe_pool;
