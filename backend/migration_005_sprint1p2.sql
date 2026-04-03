-- MIGRATION 005 — Sprint 1 Part 2: Trading Engine Tables
-- New tables for Rule Engine, Market Regime, Position Manager, Paper Trading, etc.

-- ═══════════════════════════════════════════════════════
-- 1. trading_rules — Editable trading rules (Aa11-Bb23)
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS trading_rules (
    id              BIGINT PRIMARY KEY,
    rule_code       VARCHAR(10) NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    direction       VARCHAR(10),
    market_type     JSONB DEFAULT '["crypto_spot", "crypto_futures"]'::jsonb,
    ema50_vs_ema200 VARCHAR(10) DEFAULT 'any',
    enabled         BOOLEAN DEFAULT true,
    regime_allowed  JSONB DEFAULT '["bajo_riesgo", "riesgo_medio"]'::jsonb,
    priority        INT DEFAULT 99,
    confidence      VARCHAR(15),
    entry_trades    JSONB DEFAULT '[1]'::jsonb,
    conditions      JSONB DEFAULT '[]'::jsonb,
    logic           VARCHAR(5) DEFAULT 'AND',
    notes           TEXT,
    version         INT DEFAULT 1,
    current         BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_trading_rules_updated_at ON trading_rules;
CREATE TRIGGER update_trading_rules_updated_at
BEFORE UPDATE ON trading_rules
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ═══════════════════════════════════════════════════════
-- 2. trading_rules_history — Version control for rules
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS trading_rules_history (
    id                  BIGSERIAL PRIMARY KEY,
    rule_id             BIGINT REFERENCES trading_rules(id),
    version             INT,
    changed_at          TIMESTAMPTZ DEFAULT NOW(),
    changed_by          TEXT DEFAULT 'system',
    previous_config     JSONB,
    new_config          JSONB,
    reason              TEXT,
    performance_before  JSONB,
    performance_after   JSONB
);

-- ═══════════════════════════════════════════════════════
-- 3. market_regime — Current and historical regime data
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS market_regime (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(30) NOT NULL,
    category        VARCHAR(20) NOT NULL,
    risk_score      NUMERIC(6,2),
    label           VARCHAR(30),
    features        JSONB,
    evaluated_at    TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_market_regime_symbol UNIQUE (symbol)
);

CREATE INDEX IF NOT EXISTS idx_market_regime_symbol ON market_regime(symbol);

-- ═══════════════════════════════════════════════════════
-- 4. paper_trades — Paper trading records
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS paper_trades (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol              VARCHAR(30) NOT NULL,
    side                VARCHAR(10) NOT NULL,
    entry_price         NUMERIC(20,8),
    sl_price            NUMERIC(20,8),
    tp_price            NUMERIC(20,8),
    exit_price          NUMERIC(20,8),
    exit_reason         VARCHAR(30),
    pnl_usd             NUMERIC(20,8),
    pnl_pct             NUMERIC(8,4),
    rule_code           VARCHAR(10),
    regime              VARCHAR(20),
    ema20_phase         VARCHAR(30),
    adx_value           NUMERIC(8,4),
    confluence_score    INT,
    ai_recommendation   VARCHAR(20),
    ai_agreed           BOOLEAN,
    opened_at           TIMESTAMPTZ DEFAULT NOW(),
    closed_at           TIMESTAMPTZ,
    bars_held           INT,
    mode                VARCHAR(10) DEFAULT 'paper',
    trade_sizes         JSONB,
    avg_entry_price     NUMERIC(20,8),
    total_usd           NUMERIC(20,8),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_paper_trades_symbol ON paper_trades(symbol, opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_trades_rule ON paper_trades(rule_code);

-- ═══════════════════════════════════════════════════════
-- 5. cooldowns — Post-SL and post-TP cooldown periods
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS cooldowns (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol          VARCHAR(30) NOT NULL,
    timeframe       VARCHAR(10) NOT NULL,
    cooldown_type   VARCHAR(20) NOT NULL,
    triggered_at    TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    active          BOOLEAN DEFAULT true,
    CONSTRAINT unique_cooldown_symbol_tf UNIQUE (symbol, timeframe)
);

CREATE INDEX IF NOT EXISTS idx_cooldowns_active ON cooldowns(symbol, active);

-- ═══════════════════════════════════════════════════════
-- 6. config_snapshots — Configuration backup/restore
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS config_snapshots (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(100),
    snapshot_data   JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    created_by      TEXT DEFAULT 'user'
);

-- ═══════════════════════════════════════════════════════
-- 7. trading_config — Unified editable trading parameters
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS trading_config (
    id              INT PRIMARY KEY DEFAULT 1,
    -- Capital
    capital_total       NUMERIC(20,2) DEFAULT 500.0,
    trading_pct         NUMERIC(5,2) DEFAULT 20.0,
    trade_distribution  JSONB DEFAULT '[0.20, 0.30, 0.50]'::jsonb,
    -- Regime params
    regime_params       JSONB DEFAULT '{
        "alto_riesgo": {"mtf_threshold": 0.80, "max_trades": 1, "atr_mult": 2.5, "rr_min": 3.0, "adx_min": 30, "min_nivel_entrada": 2, "di_cross_required": true, "flat_pct": 25.0, "peak_pct": 75.0},
        "riesgo_medio": {"mtf_threshold": 0.65, "max_trades": 3, "atr_mult": 2.0, "rr_min": 2.5, "adx_min": 20, "min_nivel_entrada": 1, "di_cross_required": true, "flat_pct": 20.0, "peak_pct": 80.0},
        "bajo_riesgo": {"mtf_threshold": 0.50, "max_trades": 5, "atr_mult": 1.5, "rr_min": 2.0, "adx_min": 15, "min_nivel_entrada": 1, "di_cross_required": false, "flat_pct": 15.0, "peak_pct": 85.0}
    }'::jsonb,
    -- Holding
    max_holding_bars    JSONB DEFAULT '{"15m": 48, "30m": 48, "1h": 32, "4h": 30, "1d": 14, "1w": 8}'::jsonb,
    signal_expiry_bars  INT DEFAULT 3,
    -- Protections
    max_daily_loss_pct  NUMERIC(5,2) DEFAULT 5.0,
    max_trade_loss_pct  NUMERIC(5,2) DEFAULT 2.0,
    cooldown_post_sl    INT DEFAULT 3,
    cooldown_post_tp    INT DEFAULT 1,
    max_correlation     NUMERIC(4,2) DEFAULT 0.80,
    vol_min_entry_pct   NUMERIC(5,2) DEFAULT 70.0,
    -- Orders
    order_type          VARCHAR(10) DEFAULT 'limit',
    limit_timeout_bars  INT DEFAULT 2,
    sl_gap_pct          NUMERIC(5,2) DEFAULT 0.10,
    fee_pct             NUMERIC(5,4) DEFAULT 0.001,
    -- Emergency
    emergency_enabled   BOOLEAN DEFAULT true,
    atr_emergency_mult  NUMERIC(4,2) DEFAULT 2.0,
    emergency_action    VARCHAR(20) DEFAULT 'alert_only',
    -- Market
    market_mode         VARCHAR(20) DEFAULT 'crypto_futures',
    leverage            INT DEFAULT 5,
    active_symbols      JSONB DEFAULT '["BTC/USDT", "ETH/USDT", "SOL/USDT", "ADA/USDT"]'::jsonb,
    -- AI
    ai_enabled          BOOLEAN DEFAULT true,
    ai_mode             VARCHAR(15) DEFAULT 'informative',
    -- Telegram
    telegram_enabled    BOOLEAN DEFAULT true,
    -- Paper trading
    paper_trading       BOOLEAN DEFAULT true,
    --
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS update_trading_config_updated_at ON trading_config;
CREATE TRIGGER update_trading_config_updated_at
BEFORE UPDATE ON trading_config
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert default config
INSERT INTO trading_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- ═══════════════════════════════════════════════════════
-- 8. Enable realtime for new tables
-- ═══════════════════════════════════════════════════════
ALTER PUBLICATION supabase_realtime ADD TABLE market_regime;
ALTER PUBLICATION supabase_realtime ADD TABLE paper_trades;
ALTER PUBLICATION supabase_realtime ADD TABLE trading_config;

-- ═══════════════════════════════════════════════════════
-- 9. Market regime history (for dashboard charts, append-only)
-- ═══════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS market_regime_history (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(30) NOT NULL,
    category        VARCHAR(20) NOT NULL,
    risk_score      NUMERIC(6,2),
    features        JSONB,
    evaluated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_regime_history ON market_regime_history(symbol, evaluated_at DESC);
