-- ============================================================
-- eTrader APEX Options - migracion opt_002 (Sprint 2: universo, contratos, cotizaciones, snapshots)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_underlyings (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL UNIQUE,
    underlying_conid    BIGINT,
    apex_score          NUMERIC,
    direction           TEXT CHECK (direction IN ('bullish','bearish','neutral')),
    price               NUMERIC,
    optionable          BOOLEAN NOT NULL DEFAULT FALSE,
    optionable_reason   TEXT,
    warnings            JSONB NOT NULL DEFAULT '[]'::jsonb,
    strike_gap_pct      NUMERIC,
    atm_spread_pct      NUMERIC,
    atm_oi              NUMERIC,
    atm_volume          NUMERIC,
    iv_hv_ratio         NUMERIC,
    event_flags         JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_state          TEXT,
    last_chain_sync_at  TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS opt_contracts (
    id              BIGSERIAL PRIMARY KEY,
    conid           BIGINT NOT NULL UNIQUE,
    underlying_id   BIGINT NOT NULL REFERENCES opt_underlyings(id) ON DELETE CASCADE,
    "right"         CHAR(1) NOT NULL CHECK ("right" IN ('C','P')),
    strike          NUMERIC NOT NULL CHECK (strike > 0),
    expiry          DATE NOT NULL,
    multiplier      INT NOT NULL DEFAULT 100 CHECK (multiplier > 0),
    trading_class   TEXT,
    exchange        TEXT,
    currency        TEXT NOT NULL DEFAULT 'USD',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_contracts_lookup ON opt_contracts (underlying_id, expiry, "right", strike);

CREATE TABLE IF NOT EXISTS opt_quotes_latest (
    contract_id        BIGINT PRIMARY KEY REFERENCES opt_contracts(id) ON DELETE CASCADE,
    bid                NUMERIC,
    ask                NUMERIC,
    last               NUMERIC,
    volume             NUMERIC,
    open_interest      NUMERIC,
    iv                 NUMERIC,
    delta              NUMERIC,
    gamma              NUMERIC,
    theta              NUMERIC,
    vega               NUMERIC,
    underlying_price   NUMERIC,
    market_data_type   TEXT NOT NULL CHECK (market_data_type IN ('LIVE','DELAYED','FROZEN','UNKNOWN','STALE','ERROR')),
    usable             BOOLEAN NOT NULL DEFAULT FALSE,
    unusable_reason    TEXT,
    received_at        TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS opt_snapshots (
    id                 BIGSERIAL PRIMARY KEY,
    contract_id        BIGINT NOT NULL REFERENCES opt_contracts(id) ON DELETE CASCADE,
    captured_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    bid                NUMERIC,
    ask                NUMERIC,
    last               NUMERIC,
    volume             NUMERIC,
    open_interest      NUMERIC,
    iv                 NUMERIC,
    delta              NUMERIC,
    gamma              NUMERIC,
    theta              NUMERIC,
    vega               NUMERIC,
    underlying_price   NUMERIC,
    market_data_type   TEXT NOT NULL,
    data_source        TEXT NOT NULL DEFAULT 'ibkr'
);
CREATE INDEX IF NOT EXISTS idx_opt_snapshots_contract_time ON opt_snapshots (contract_id, captured_at DESC);

ALTER TABLE opt_underlyings   ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_contracts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_quotes_latest ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_snapshots     ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- DROP TABLE IF EXISTS opt_snapshots, opt_quotes_latest, opt_contracts, opt_underlyings;
