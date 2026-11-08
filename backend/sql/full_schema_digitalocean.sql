-- ========================================================
-- eTrade MultiMarket v5.0 — Consolidated PostgreSQL Schema
-- Target: DigitalOcean PostgreSQL 17 + PostgREST
-- Generated: 2026-11-06
-- ========================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Roles for PostgREST
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
END
$$;


-- Core Stocks & Missing Tables
CREATE TABLE IF NOT EXISTS stocks_positions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    direction VARCHAR(10) DEFAULT 'long',
    shares NUMERIC NOT NULL DEFAULT 0,
    avg_price NUMERIC NOT NULL DEFAULT 0,
    total_cost NUMERIC DEFAULT 0,
    current_price NUMERIC DEFAULT 0,
    stop_loss NUMERIC,
    trailing_sl_price NUMERIC,
    highest_price_reached NUMERIC,
    take_profit NUMERIC,
    tp_levels JSONB,
    group_name VARCHAR(50) DEFAULT 'HOT',
    strategy VARCHAR(50),
    status VARCHAR(20) DEFAULT 'open',
    first_buy_at TIMESTAMPTZ DEFAULT NOW(),
    entry_date TIMESTAMPTZ,
    exit_date TIMESTAMPTZ,
    exit_price NUMERIC,
    exit_reason TEXT,
    exit_triggered_by TEXT,
    sl_close_reason TEXT,
    unrealized_pnl NUMERIC DEFAULT 0,
    unrealized_pnl_pct NUMERIC DEFAULT 0,
    pnl_usd NUMERIC DEFAULT 0,
    pnl_pct NUMERIC DEFAULT 0,
    slv_price NUMERIC,
    recovery_activated_at TIMESTAMPTZ,
    diagnostics JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stocks_positions_ticker_status ON stocks_positions(ticker, status);
CREATE INDEX IF NOT EXISTS idx_stocks_positions_status ON stocks_positions(status);

CREATE TABLE IF NOT EXISTS stocks_orders (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker VARCHAR(64) NOT NULL,
    group_name VARCHAR(50),
    rule_code VARCHAR(50),
    order_type VARCHAR(20) NOT NULL DEFAULT 'market',
    direction VARCHAR(10) NOT NULL,
    shares NUMERIC,
    limit_price NUMERIC,
    market_price NUMERIC,
    trigger_price NUMERIC,
    estimated_price NUMERIC,
    slippage_usd NUMERIC,
    slippage_pct NUMERIC,
    target_band VARCHAR(64),
    status VARCHAR(20) DEFAULT 'pending',
    filled_price NUMERIC,
    filled_at TIMESTAMPTZ,
    ia_score NUMERIC,
    tech_score NUMERIC,
    movement_type VARCHAR(30),
    rvol NUMERIC,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stocks_orders_status ON stocks_orders(status);
CREATE INDEX IF NOT EXISTS idx_stocks_orders_ticker ON stocks_orders(ticker, created_at DESC);

CREATE TABLE IF NOT EXISTS stocks_rules (
    id SERIAL PRIMARY KEY,
    rule_code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    group_name VARCHAR(50),
    direction VARCHAR(10) NOT NULL DEFAULT 'buy',
    order_type VARCHAR(10) NOT NULL DEFAULT 'market',
    enabled BOOLEAN DEFAULT true,
    priority INT DEFAULT 1,
    ia_min NUMERIC DEFAULT 7,
    tech_score_min NUMERIC DEFAULT 60,
    movements_allowed TEXT[],
    pine_signal VARCHAR(20),
    pine_required BOOLEAN DEFAULT false,
    fib_trigger INT[],
    rvol_min NUMERIC DEFAULT 0.0,
    limit_trigger_pct NUMERIC DEFAULT 0.005,
    close_all BOOLEAN DEFAULT false,
    dca_enabled BOOLEAN DEFAULT false,
    dca_max_buys INT DEFAULT 3,
    dca_min_drop_pct NUMERIC DEFAULT 1.0,
    notes TEXT,
    description TEXT,
    parameters JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stocks_priority_queue (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker VARCHAR(30) NOT NULL UNIQUE,
    group_name VARCHAR(50),
    apex_score_4h NUMERIC DEFAULT 50 NOT NULL,
    apex_score_1d NUMERIC DEFAULT 50 NOT NULL,
    return_expected NUMERIC DEFAULT 0,
    confidence VARCHAR(20),
    composite_rank NUMERIC DEFAULT 0 NOT NULL,
    priority_score NUMERIC DEFAULT 0,
    status VARCHAR(50) DEFAULT 'pending',
    entry_reason VARCHAR(100),
    triggered_rule VARCHAR(50),
    is_overbought BOOLEAN DEFAULT false,
    rsi_at_entry NUMERIC,
    fib_zone INT,
    capital_assigned NUMERIC DEFAULT 0,
    shares_target INT DEFAULT 0,
    price_at_rank NUMERIC,
    stop_loss_trigger NUMERIC,
    tactical_target_ceiling NUMERIC,
    tactical_target_floor NUMERIC,
    movement_type VARCHAR(30),
    rvol NUMERIC,
    entered_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    bought_at TIMESTAMPTZ,
    exited_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stocks_groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stocks_watchlist (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) UNIQUE NOT NULL,
    group_name VARCHAR(50),
    company_name VARCHAR(100),
    sector VARCHAR(50),
    enabled BOOLEAN DEFAULT true,
    pool_type VARCHAR(20) DEFAULT 'HOT',
    is_active BOOLEAN DEFAULT true,
    notes TEXT,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS opt_user_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS universe_settings (
    id INT PRIMARY KEY,
    fg_mcap_min NUMERIC DEFAULT 300,
    fg_mcap_max NUMERIC DEFAULT 10000,
    fg_rev_growth_min NUMERIC DEFAULT 25,
    fg_price_max NUMERIC DEFAULT 50,
    fg_rs_min NUMERIC DEFAULT 70,
    gl_mcap_min NUMERIC DEFAULT 5000,
    gl_rev_growth_min NUMERIC DEFAULT 12,
    gl_margin_min NUMERIC DEFAULT 30,
    gl_rs_min NUMERIC DEFAULT 75,
    gl_inst_min NUMERIC DEFAULT 40,
    gl_price_max NUMERIC DEFAULT 200,
    ex_vol_min NUMERIC DEFAULT 200000,
    ex_debt_equity_max NUMERIC DEFAULT 3.0,
    ex_eps_neg_quarters_max INT DEFAULT 4,
    w_rev_growth NUMERIC DEFAULT 25,
    w_gross_margin NUMERIC DEFAULT 20,
    w_eps_growth NUMERIC DEFAULT 20,
    w_rs_score NUMERIC DEFAULT 20,
    w_inst_ownership NUMERIC DEFAULT 15,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS retention_config (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) UNIQUE NOT NULL,
    retention_days INT DEFAULT 30,
    is_active BOOLEAN DEFAULT true,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sl_orders (
    id BIGSERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    sl_price NUMERIC NOT NULL,
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS apex_scores (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    calculated_at TIMESTAMPTZ DEFAULT NOW(),
    price_at_calc NUMERIC,
    b1_momentum NUMERIC,
    b2_technical NUMERIC,
    b3_fundamental NUMERIC,
    b4_regime NUMERIC,
    b5_sentiment NUMERIC,
    apex_score_4h NUMERIC,
    apex_score_1d NUMERIC,
    return_expected_4h NUMERIC,
    return_expected_1d NUMERIC,
    confidence VARCHAR(20),
    regime_type VARCHAR(30),
    edge_pct NUMERIC,
    scenario_bull JSONB,
    scenario_base JSONB,
    scenario_bear JSONB,
    detail JSONB,
    valid_until_4h TIMESTAMPTZ,
    valid_until_1d TIMESTAMPTZ,
    actual_return_4h NUMERIC,
    actual_return_1d NUMERIC,
    prediction_correct BOOLEAN,
    b6_growth NUMERIC,
    xg_score NUMERIC,
    xg_detail JSONB,
    timing_score NUMERIC,
    timing_detail JSONB,
    trade_score NUMERIC,
    etv NUMERIC,
    upside_expected NUMERIC,
    downside_risk NUMERIC,
    peg_ratio NUMERIC,
    fcf_yield NUMERIC,
    market_cap_tier VARCHAR(20),
    apex_score NUMERIC,
    apex_signal VARCHAR(20),
    apex_confidence NUMERIC,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS options_positions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    contracts NUMERIC DEFAULT 1,
    status VARCHAR(20) DEFAULT 'open',
    entry_price NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS eti_signals (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    signal_type VARCHAR(20),
    confidence NUMERIC,
    data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_config (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trading_state (
    id SERIAL PRIMARY KEY,
    market VARCHAR(50) UNIQUE NOT NULL,
    state JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS db_cleanup_log (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(100),
    deleted_rows INT,
    executed_at TIMESTAMPTZ DEFAULT NOW()
);


-- ════════════════════════════════════════════════
-- Forex Execution Service — Tablas de Posiciones
-- ════════════════════════════════════════════════

-- Posiciones Forex abiertas/cerradas
CREATE TABLE IF NOT EXISTS forex_positions (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol           VARCHAR(10) NOT NULL,
    side             VARCHAR(10) NOT NULL,          -- 'long' | 'short'
    lots             NUMERIC NOT NULL,
    entry_price      NUMERIC NOT NULL,
    sl_price         NUMERIC,
    tp_price         NUMERIC,
    current_price    NUMERIC,
    unrealized_pnl   NUMERIC DEFAULT 0,
    pips_pnl         NUMERIC DEFAULT 0,
    rule_code        VARCHAR(20),
    ctrader_order_id BIGINT,
    ctrader_pos_id   BIGINT,
    status           VARCHAR(20) DEFAULT 'open',    -- open | closed | pending
    opened_at        TIMESTAMPTZ DEFAULT NOW(),
    closed_at        TIMESTAMPTZ,
    close_reason     VARCHAR(50),                   -- sl | tp | sar_phase_change | max_holding | manual
    pnl_usd          NUMERIC DEFAULT 0,
    pnl_pips         NUMERIC DEFAULT 0,
    market_type      VARCHAR(30) DEFAULT 'forex_futures',
    mode             VARCHAR(20) DEFAULT 'paper'    -- paper | live
);

-- Índices para consultas rápidas
CREATE INDEX IF NOT EXISTS idx_forex_positions_symbol
    ON forex_positions(symbol, status);

CREATE INDEX IF NOT EXISTS idx_forex_positions_status
    ON forex_positions(status);

-- Órdenes Forex (LIMIT/STOP orders)
CREATE TABLE IF NOT EXISTS forex_orders (
    id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol           VARCHAR(10) NOT NULL,
    order_type       VARCHAR(10) NOT NULL,          -- 'market' | 'limit' | 'stop'
    side             VARCHAR(10) NOT NULL,
    lots             NUMERIC NOT NULL,
    limit_price      NUMERIC,
    sl_price         NUMERIC,
    tp_price         NUMERIC,
    rule_code        VARCHAR(20),
    status           VARCHAR(20) DEFAULT 'pending', -- pending | filled | cancelled | expired
    ctrader_order_id BIGINT,
    filled_price     NUMERIC,
    filled_at        TIMESTAMPTZ,
    expires_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Verificar creación
SELECT table_name
FROM information_schema.tables
WHERE table_name IN ('forex_positions', 'forex_orders');


-- >>> migration_001_initial.sql >>>
-- MIGRATION 001 - Initial Setup

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- 1. Helper function for updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. api_connections
CREATE TABLE api_connections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange VARCHAR(50) NOT NULL,
    api_key TEXT NOT NULL,
    api_secret TEXT NOT NULL,
    environment VARCHAR(10) DEFAULT 'paper',
    rate_limit INTEGER DEFAULT 1200,
    status VARCHAR(20) DEFAULT 'active',
    last_ping TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER update_api_connections_updated_at
BEFORE UPDATE ON api_connections
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 3. system_config
CREATE TABLE system_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key VARCHAR(100) UNIQUE NOT NULL,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER update_system_config_updated_at
BEFORE UPDATE ON system_config
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 4. market_candles
CREATE TABLE market_candles (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(30) NOT NULL,
    exchange VARCHAR(50) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    open_time TIMESTAMPTZ NOT NULL,
    open NUMERIC(20,8) NOT NULL,
    high NUMERIC(20,8) NOT NULL,
    low NUMERIC(20,8) NOT NULL,
    close NUMERIC(20,8) NOT NULL,
    volume NUMERIC(30,8) NOT NULL,
    quote_volume NUMERIC(30,8),
    trades_count INTEGER,
    taker_buy_volume NUMERIC(30,8),
    taker_sell_volume NUMERIC(30,8),
    CONSTRAINT unique_market_candle UNIQUE (symbol, exchange, timeframe, open_time)
);
CREATE INDEX idx_market_candles ON market_candles(symbol, timeframe, open_time DESC);

-- 5. volume_spikes
CREATE TABLE volume_spikes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(30) NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL,
    candle_open NUMERIC(20,8) NOT NULL,
    candle_close NUMERIC(20,8) NOT NULL,
    candle_volume NUMERIC(30,8) NOT NULL,
    avg_volume_20 NUMERIC(30,8) NOT NULL,
    spike_ratio NUMERIC(8,4) NOT NULL,
    spike_direction VARCHAR(15) NOT NULL,
    taker_buy_pct NUMERIC(5,2),
    body_pct NUMERIC(5,2),
    resulted_in_signal BOOLEAN DEFAULT false,
    mtf_score NUMERIC(5,4),
    cycle_id UUID
);

-- 6. technical_indicators
CREATE TABLE technical_indicators (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(30) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    ema_3 NUMERIC(20,8),
    ema_9 NUMERIC(20,8),
    ema_20 NUMERIC(20,8),
    ema_50 NUMERIC(20,8),
    ema_200 NUMERIC(20,8),
    rsi_14 NUMERIC(8,4),
    macd_line NUMERIC(20,8),
    macd_signal NUMERIC(20,8),
    macd_histogram NUMERIC(20,8),
    bb_upper NUMERIC(20,8),
    bb_middle NUMERIC(20,8),
    bb_lower NUMERIC(20,8),
    atr_14 NUMERIC(20,8),
    adx_14 NUMERIC(8,4),
    di_plus NUMERIC(8,4),
    di_minus NUMERIC(8,4),
    vwap NUMERIC(20,8),
    stoch_k NUMERIC(8,4),
    stoch_d NUMERIC(8,4),
    williams_r NUMERIC(8,4),
    volume_sma_20 NUMERIC(30,8),
    CONSTRAINT unique_technical_indicator UNIQUE (symbol, timeframe, timestamp)
);
CREATE INDEX idx_technical_indicators ON technical_indicators(symbol, timeframe, timestamp DESC);

-- 7. candle_patterns
CREATE TABLE candle_patterns (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(30) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    pattern_name VARCHAR(50) NOT NULL,
    pattern_type VARCHAR(10) NOT NULL,
    pattern_strength NUMERIC(5,2),
    timestamp TIMESTAMPTZ NOT NULL
);

-- 8. trading_signals
CREATE TABLE trading_signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    spike_id UUID REFERENCES volume_spikes(id),
    symbol VARCHAR(30) NOT NULL,
    signal_type VARCHAR(10) NOT NULL,
    mtf_score NUMERIC(5,4) NOT NULL,
    sentiment_adjustment NUMERIC(5,4),
    score_final NUMERIC(5,4) NOT NULL,
    vote_15m INTEGER NOT NULL,
    vote_30m INTEGER NOT NULL,
    vote_45m INTEGER NOT NULL,
    vote_4h INTEGER NOT NULL,
    vote_1d INTEGER NOT NULL,
    vote_1w INTEGER NOT NULL,
    entry_price NUMERIC(20,8),
    stop_loss NUMERIC(20,8) NOT NULL,
    take_profit NUMERIC(20,8) NOT NULL,
    atr_4h_used NUMERIC(20,8),
    risk_reward_ratio NUMERIC(6,2),
    status VARCHAR(20) DEFAULT 'pending',
    rejection_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 9. risk_config
CREATE TABLE risk_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    max_risk_per_trade_pct NUMERIC(5,2) DEFAULT 1.0,
    max_daily_loss_pct NUMERIC(5,2) DEFAULT 5.0,
    max_open_trades INTEGER DEFAULT 3,
    sl_multiplier NUMERIC(4,2) DEFAULT 2.0,
    rr_ratio NUMERIC(4,2) DEFAULT 2.5,
    kill_switch_enabled BOOLEAN DEFAULT true,
    kill_switch_loss_pct NUMERIC(5,2) DEFAULT 3.0,
    slippage_estimate_pct NUMERIC(5,4) DEFAULT 0.05,
    bot_active BOOLEAN DEFAULT true,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER update_risk_config_updated_at
BEFORE UPDATE ON risk_config
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 10. orders
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    exchange_order_id VARCHAR(100),
    oco_list_client_id VARCHAR(100),
    signal_id UUID REFERENCES trading_signals(id),
    symbol VARCHAR(30) NOT NULL,
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    quantity NUMERIC(20,8) NOT NULL,
    entry_price NUMERIC(20,8),
    stop_loss_price NUMERIC(20,8) NOT NULL,
    take_profit_price NUMERIC(20,8) NOT NULL,
    commission NUMERIC(20,8),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

-- 11. positions
CREATE TABLE positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID REFERENCES orders(id),
    symbol VARCHAR(30) NOT NULL,
    side VARCHAR(10) NOT NULL,
    entry_price NUMERIC(20,8) NOT NULL,
    current_price NUMERIC(20,8),
    size NUMERIC(20,8) NOT NULL,
    stop_loss NUMERIC(20,8) NOT NULL,
    take_profit NUMERIC(20,8) NOT NULL,
    unrealized_pnl NUMERIC(20,8),
    realized_pnl NUMERIC(20,8),
    close_reason VARCHAR(20),
    status VARCHAR(20) DEFAULT 'open',
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ
);

-- 12. news_sentiment
CREATE TABLE news_sentiment (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(30) NOT NULL,
    cycle_id UUID NOT NULL,
    news_headlines TEXT[],
    gemini_response TEXT,
    sentiment_score NUMERIC(4,2),
    confidence NUMERIC(5,4),
    key_factors TEXT[],
    analyzed_at TIMESTAMPTZ DEFAULT NOW()
);

-- 13. backtest_runs
CREATE TABLE backtest_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    strategy_name VARCHAR(100) NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital NUMERIC(20,2) NOT NULL,
    final_capital NUMERIC(20,2),
    total_return_pct NUMERIC(10,4),
    win_rate NUMERIC(5,2),
    profit_factor NUMERIC(10,4),
    sharpe_ratio NUMERIC(10,4),
    max_drawdown_pct NUMERIC(8,4),
    total_trades INTEGER,
    params_used JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 14. alert_events
CREATE TABLE alert_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(50) NOT NULL,
    symbol VARCHAR(30),
    message TEXT NOT NULL,
    data JSONB,
    severity VARCHAR(10) NOT NULL,
    telegram_sent BOOLEAN DEFAULT false,
    email_sent BOOLEAN DEFAULT false,
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- 15. cron_cycles
CREATE TABLE cron_cycles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    duration_seconds NUMERIC(8,2),
    symbols_analyzed INTEGER,
    spikes_detected INTEGER,
    signals_generated INTEGER,
    orders_executed INTEGER,
    errors INTEGER DEFAULT 0,
    status VARCHAR(20),
    notes TEXT
);

-- 16. system_logs
CREATE TABLE system_logs (
    id BIGSERIAL PRIMARY KEY,
    cycle_id UUID,
    module VARCHAR(50) NOT NULL,
    level VARCHAR(10) NOT NULL,
    message TEXT NOT NULL,
    context JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS Enablement
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_signals ENABLE ROW LEVEL SECURITY;

-- Supabase realtime replication
-- ALTER PUBLICATION supabase_realtime ADD TABLE trading_signals;
-- ALTER PUBLICATION supabase_realtime ADD TABLE positions;
-- ALTER PUBLICATION supabase_realtime ADD TABLE alert_events;
-- ALTER PUBLICATION supabase_realtime ADD TABLE cron_cycles;

-- Insert initial values
INSERT INTO risk_config (max_risk_per_trade_pct, max_daily_loss_pct, max_open_trades, sl_multiplier, rr_ratio, kill_switch_enabled, kill_switch_loss_pct, slippage_estimate_pct, bot_active)
VALUES (1.0, 5.0, 3, 2.0, 2.5, true, 3.0, 0.05, true);

INSERT INTO system_config (key, value, description) VALUES
('spike_multiplier', '2.5', 'Umbral de deteccion de volumen'),
('mtf_signal_threshold', '0.65', 'Score minimo para generar senal'),
('sl_multiplier', '2.0', 'Multiplicador ATR para Stop Loss'),
('rr_ratio', '2.5', 'Risk/Reward ratio minimo'),
('max_risk_per_trade', '0.01', '1% del balance por trade'),
('top_symbols', '20', 'Nro de simbolos activos'),
('candle_history_days', '90', 'Dias de retencion para 15m/30m/45m');

-- Data retention cleanup function and trigger using pg_cron
CREATE OR REPLACE FUNCTION limpieza_candles_historicos()
RETURNS void AS $$
BEGIN
    DELETE FROM market_candles WHERE timeframe IN ('15m','30m','45m') AND open_time < now() - interval '90 days';
    DELETE FROM system_logs WHERE created_at < now() - interval '30 days';
END;
$$ LANGUAGE plpgsql;

-- Schedule the cron job to run once a week
SELECT cron.schedule('hebdomadal-cleanup', '0 0 * * 0', 'SELECT limpieza_candles_historicos();');

-- <<< migration_001_initial.sql <<<


-- >>> migration_002_retention.sql >>>
-- MIGRATION 002 - Data Retention (Sprint 2 - S2-07)
-- ================================================================
-- Implements a comprehensive data retention policy to keep
-- Supabase Free plan within the 500 MB limit.
-- ================================================================

-- Drop old function if exists (from migration 001)
DROP FUNCTION IF EXISTS limpieza_candles_historicos();

-- ── 1. Create comprehensive cleanup function ──
CREATE OR REPLACE FUNCTION clean_old_candles()
RETURNS void AS $$
BEGIN
  -- Eliminar candles de 15m/30m/45m con más de 90 días
  DELETE FROM market_candles
  WHERE timeframe IN ('15m', '30m', '45m')
  AND open_time < NOW() - INTERVAL '90 days';

  -- Eliminar logs de más de 30 días
  DELETE FROM system_logs
  WHERE created_at < NOW() - INTERVAL '30 days';

  -- Eliminar ciclos de más de 90 días
  DELETE FROM cron_cycles
  WHERE started_at < NOW() - INTERVAL '90 days';

  -- Eliminar volume_spikes de más de 60 días
  DELETE FROM volume_spikes
  WHERE detected_at < NOW() - INTERVAL '60 days';

  -- Eliminar technical_indicators de más de 90 días
  DELETE FROM technical_indicators
  WHERE timestamp < NOW() - INTERVAL '90 days';
END;
$$ LANGUAGE plpgsql;

-- ── 2. Enable pg_cron extension (if not already enabled) ──
-- NOTE: pg_cron must be enabled from Supabase Dashboard:
-- Dashboard → Database → Extensions → search "pg_cron" → Toggle ON
-- The CREATE EXTENSION command may fail in Supabase; enable via UI instead.
-- CREATE EXTENSION IF NOT EXISTS pg_cron;

-- ── 3. Remove old cron job if exists ──
-- SELECT cron.unschedule('hebdomadal-cleanup');

-- ── 4. Schedule weekly cleanup: Sundays at 3am UTC ──
SELECT cron.schedule(
  'weekly-candle-cleanup',
  '0 3 * * 0',  -- Sundays at 3:00 AM UTC
  'SELECT clean_old_candles()'
);

-- ── 5. Execute manually on first run ──
SELECT clean_old_candles();

-- ── 6. Verify table sizes ──
-- Run this manually after migration to check:
-- SELECT
--   schemaname,
--   tablename,
--   pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
-- FROM pg_tables
-- WHERE schemaname = 'public'
-- ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- ── 7. Add excluded_symbols to system_config ──
INSERT INTO system_config (key, value, description)
VALUES (
  'excluded_symbols',
  '["FDUSDUSDT", "USDCUSDT", "BUSDUSDT", "TUSDUSDT", "USDPUSDT", "DAIUSDT", "USDDUSDT", "EURCUSDT", "PAXGUSDT"]'::jsonb,
  'Lista de stablecoins excluidas del análisis'
)
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    description = EXCLUDED.description;

-- <<< migration_002_retention.sql <<<


-- >>> migration_003_sprint3.sql >>>
-- ═══════════════════════════════════════════════════════
-- eTrader v2 — Migration 003: Sprint 3 tables & columns
-- Run this in the Supabase SQL Editor
-- ═══════════════════════════════════════════════════════

-- ── news_sentiment table (for Gemini sentiment analysis) ──
CREATE TABLE IF NOT EXISTS news_sentiment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    cycle_id UUID,
    news_headlines JSONB DEFAULT '[]',
    gemini_response TEXT,
    sentiment_score FLOAT DEFAULT 0.0,
    confidence FLOAT DEFAULT 0.0,
    key_factors JSONB DEFAULT '[]',
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_sentiment_symbol ON news_sentiment(symbol);
CREATE INDEX IF NOT EXISTS idx_news_sentiment_cycle ON news_sentiment(cycle_id);

-- ── candle_patterns table ──
CREATE TABLE IF NOT EXISTS candle_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    pattern_name TEXT NOT NULL,
    pattern_type TEXT NOT NULL,
    pattern_strength FLOAT DEFAULT 0.0,
    timestamp TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_candle_patterns_symbol ON candle_patterns(symbol);

-- ── Ensure trading_signals has all required columns ──
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_signals' AND column_name = 'sentiment_adjustment') THEN
        ALTER TABLE trading_signals ADD COLUMN sentiment_adjustment FLOAT DEFAULT 0.0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_signals' AND column_name = 'score_final') THEN
        ALTER TABLE trading_signals ADD COLUMN score_final FLOAT DEFAULT 0.0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_signals' AND column_name = 'vote_15m') THEN
        ALTER TABLE trading_signals ADD COLUMN vote_15m INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_signals' AND column_name = 'vote_30m') THEN
        ALTER TABLE trading_signals ADD COLUMN vote_30m INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_signals' AND column_name = 'vote_45m') THEN
        ALTER TABLE trading_signals ADD COLUMN vote_45m INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_signals' AND column_name = 'vote_4h') THEN
        ALTER TABLE trading_signals ADD COLUMN vote_4h INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_signals' AND column_name = 'vote_1d') THEN
        ALTER TABLE trading_signals ADD COLUMN vote_1d INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_signals' AND column_name = 'vote_1w') THEN
        ALTER TABLE trading_signals ADD COLUMN vote_1w INT DEFAULT 0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_signals' AND column_name = 'atr_4h_used') THEN
        ALTER TABLE trading_signals ADD COLUMN atr_4h_used FLOAT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_signals' AND column_name = 'risk_reward_ratio') THEN
        ALTER TABLE trading_signals ADD COLUMN risk_reward_ratio FLOAT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trading_signals' AND column_name = 'rejection_reason') THEN
        ALTER TABLE trading_signals ADD COLUMN rejection_reason TEXT;
    END IF;
END $$;

-- ── Ensure cron_cycles has signals_generated column ──
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'cron_cycles' AND column_name = 'signals_generated') THEN
        ALTER TABLE cron_cycles ADD COLUMN signals_generated INT DEFAULT 0;
    END IF;
END $$;

-- ── Ensure volume_spikes has mtf_score column ──
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'volume_spikes' AND column_name = 'mtf_score') THEN
        ALTER TABLE volume_spikes ADD COLUMN mtf_score FLOAT;
    END IF;
END $$;

-- ── Enable Realtime for Sprint 3 tables ──
-- ALTER PUBLICATION supabase_realtime ADD TABLE trading_signals;
-- ALTER PUBLICATION supabase_realtime ADD TABLE volume_spikes;
-- ALTER PUBLICATION supabase_realtime ADD TABLE news_sentiment;

-- Done!
SELECT 'Migration 003 (Sprint 3) completed successfully' AS status;

-- <<< migration_003_sprint3.sql <<<


-- >>> migration_004_deduplication.sql >>>
-- ═══════════════════════════════════════════════════════
-- eTrader v2 — Migration 004: Deduplication
-- Run this in the Supabase SQL Editor
-- ═══════════════════════════════════════════════════════

-- 1. Reassign signals that point to duplicate spikes to the "main" spike ID
WITH mapping AS (
    SELECT id as duplicate_id,
           first_value(id) OVER (PARTITION BY symbol, detected_at ORDER BY id) as main_id
    FROM volume_spikes
)
UPDATE trading_signals t
SET spike_id = m.main_id
FROM mapping m
WHERE t.spike_id = m.duplicate_id
AND m.duplicate_id <> m.main_id;

-- 2. Now safe to delete duplicate spikes
DELETE FROM volume_spikes a USING (
    SELECT id, 
           row_number() OVER (PARTITION BY symbol, detected_at ORDER BY id) as row_num
    FROM volume_spikes
) b
WHERE a.id = b.id 
AND b.row_num > 1;

-- 3. Add unique constraint
ALTER TABLE volume_spikes ADD CONSTRAINT unique_symbol_detected_at UNIQUE (symbol, detected_at);

-- 3. Optimization for trading_signals (if needed)
-- ALTER TABLE trading_signals ADD CONSTRAINT unique_signal_symbol_time UNIQUE (symbol, created_at);

SELECT 'Migration 004 (Deduplication) completed' as status;

-- <<< migration_004_deduplication.sql <<<


-- >>> migration_005_sprint1p2.sql >>>
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
-- ALTER PUBLICATION supabase_realtime ADD TABLE market_regime;
-- ALTER PUBLICATION supabase_realtime ADD TABLE paper_trades;
-- ALTER PUBLICATION supabase_realtime ADD TABLE trading_config;

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

-- <<< migration_005_sprint1p2.sql <<<


-- >>> migration_006_pilot_diagnostics.sql >>>
-- MIGRATION 006 — Pilot Diagnostics
-- Table to store high-detail logs for the first 48 hours of pilot run.

CREATE TABLE IF NOT EXISTS pilot_diagnostics (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp           TIMESTAMPTZ DEFAULT NOW(),
    symbol              VARCHAR(30) NOT NULL,
    regime_category     VARCHAR(20),
    risk_score          NUMERIC(6,2),
    ema20_phase         VARCHAR(30),
    adx                 NUMERIC(8,4),
    basis_15m           NUMERIC(20,8),
    basis_4h            NUMERIC(20,8),
    signal_pinescript   VARCHAR(10),
    rule_evaluated      VARCHAR(50),
    rule_triggered      VARCHAR(50),
    entry_blocked_by    TEXT,
    ai_recommendation   VARCHAR(20),
    full_market_data    JSONB,
    observe_only        BOOLEAN DEFAULT true
);

CREATE INDEX IF NOT EXISTS idx_pilot_diag_ts ON pilot_diagnostics(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pilot_diag_sym ON pilot_diagnostics(symbol);

-- Enable realtime for the monitor dashboard
-- ALTER PUBLICATION supabase_realtime ADD TABLE pilot_diagnostics;

-- <<< migration_006_pilot_diagnostics.sql <<<


-- >>> migration_007_pilot_diagnostics_extended.sql >>>
-- MIGRATION 007 — Extended Pilot Diagnostics & Cache Invalidation
-- Adds performance and specialized logic columns requested for Sprint 1 part 2 validation.

ALTER TABLE pilot_diagnostics 
ADD COLUMN IF NOT EXISTS cycle_type       VARCHAR(5) DEFAULT '15m',
ADD COLUMN IF NOT EXISTS cycle_duration_ms INTEGER,
ADD COLUMN IF NOT EXISTS mtf_score        NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS signal_age_bars  INTEGER,
ADD COLUMN IF NOT EXISTS ai_pattern       TEXT,
ADD COLUMN IF NOT EXISTS ai_agreed        BOOLEAN;

-- Ensure trading_rules table has realtime enabled for cache invalidation
-- ALTER PUBLICATION supabase_realtime ADD TABLE trading_rules;

-- <<< migration_007_pilot_diagnostics_extended.sql <<<


-- >>> migration_008_v4_state.sql >>>
-- MIGRATION 008 — v4 Memory-First Position Management
-- Table to store current operational state (WARM data) for v4 bot.
-- Mirrors BOT_STATE.positions from Python memory.

CREATE TABLE IF NOT EXISTS bot_state (
    symbol              VARCHAR(30) PRIMARY KEY,
    side                VARCHAR(10),
    avg_entry_price     NUMERIC(20,8),
    total_usd           NUMERIC(20,8),
    sl_price            NUMERIC(20,8),
    tp_partial          NUMERIC(20,8), -- upper_5
    tp_full             NUMERIC(20,8), -- upper_6
    is_open             BOOLEAN DEFAULT false,
    breakeven_active    BOOLEAN DEFAULT false,
    entries             JSONB DEFAULT '[]', -- List of {trade_n, price, usd_amount, timestamp, rule_code}
    last_updated        TIMESTAMPTZ DEFAULT NOW()
);

-- Table for circuit breaker and global state
CREATE TABLE IF NOT EXISTS bot_global_state (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    circuit_triggered   BOOLEAN DEFAULT false,
    daily_pnl           NUMERIC(20,8) DEFAULT 0.0,
    last_reset          DATE DEFAULT CURRENT_DATE,
    emergency_mode      BOOLEAN DEFAULT false,
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT singleton CHECK (id = 1)
);

-- Log table for closed trades (COLD data)
CREATE TABLE IF NOT EXISTS trades_history (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol              VARCHAR(30) NOT NULL,
    side                VARCHAR(10) NOT NULL,
    entries             JSONB NOT NULL,
    exit_price          NUMERIC(20,8),
    exit_reason         VARCHAR(30),
    realized_pnl        NUMERIC(20,8),
    roi_pct             NUMERIC(10,4),
    opened_at           TIMESTAMPTZ NOT NULL,
    closed_at           TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Realtime for bot_state to allow dashboard updates
-- ALTER PUBLICATION supabase_realtime ADD TABLE bot_state;
-- ALTER PUBLICATION supabase_realtime ADD TABLE bot_global_state;

-- <<< migration_008_v4_state.sql <<<


-- >>> migration_009_cleanup.sql >>>
-- MIGRATION 009 — Data Cleanup for Memory-First Architecture
-- This script purges non-relevant historical data that is no longer needed 
-- under the v4 Memory-First (DB-Last) architecture.

-- 1. Purge OHLCV data (Now HOT data, stored in memory)
TRUNCATE TABLE market_candles;

-- 2. Purge Indicator data (Now calculated in memory)
TRUNCATE TABLE technical_indicators;

-- 3. Purge Volume Spike detections (Volatile analysis)
TRUNCATE TABLE volume_spikes CASCADE;

-- 4. Purge old diagnostic/pilot logs to start fresh
TRUNCATE TABLE pilot_diagnostics;

-- 5. Purge old signals (keeping only a clean state for the pilot)
TRUNCATE TABLE trading_signals CASCADE;

-- 6. Optional: Reset WARM state if you want a complete fresh start
-- TRUNCATE TABLE bot_state;
-- TRUNCATE TABLE bot_global_state;

-- <<< migration_009_cleanup.sql <<<


-- >>> migration_010_sprint1_master_schema.sql >>>
-- ==========================================================
-- MIGRATION 010 — eTrade Sprint 1 Master Schema
-- Optimized for Supabase (Memory-First Architecture)
-- ==========================================================

-- PARTE 1: ALTER TABLE (Columnas Faltantes)
-- 1.1 Tabla: positions
ALTER TABLE positions ADD COLUMN IF NOT EXISTS avg_entry_price        NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS sl_price               NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS tp_partial_price       NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS tp_full_price          NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS breakeven_activated    BOOLEAN DEFAULT false;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS breakeven_price        NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS basis_15m              NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS basis_4h               NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS basis_1d               NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS confluence_score       SMALLINT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS sizing_multiplier      NUMERIC(4,2);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS liquidation_price      NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS leverage               SMALLINT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS funding_rate_accrued   NUMERIC(10,6) DEFAULT 0;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS market_type            VARCHAR(20);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS rule_code              VARCHAR(10);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS entry_bar_index        BIGINT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS bars_held              INT DEFAULT 0;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS max_holding_bars       INT;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_closed         BOOLEAN DEFAULT false;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_close_price    NUMERIC(20,8);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_close_usd      NUMERIC(10,2);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS partial_close_at       TIMESTAMPTZ;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS entries                JSONB DEFAULT '[]'::jsonb;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS ema20_phase_entry      VARCHAR(20);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS adx_value_entry        NUMERIC(6,2);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS regime_entry           VARCHAR(20);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS realized_pnl_usd      NUMERIC(10,4);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS realized_pnl_pct       NUMERIC(8,4);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS close_reason           VARCHAR(50);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS close_bar_index        BIGINT;

-- 1.2 Tabla: orders
ALTER TABLE orders ADD COLUMN IF NOT EXISTS signal_price         NUMERIC(20,8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS execution_price      NUMERIC(20,8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS slippage_pct         NUMERIC(8,4);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_type           VARCHAR(10);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS timeout_bars         SMALLINT DEFAULT 2;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS fill_pct             NUMERIC(5,2) DEFAULT 0;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS step_number          SMALLINT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS trade_n              SMALLINT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS rule_code            VARCHAR(10);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_paper             BOOLEAN DEFAULT false;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS stop_price           NUMERIC(20,8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS limit_price          NUMERIC(20,8);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS gap_pct              NUMERIC(5,3);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS expires_at_bar       BIGINT;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancelled_reason     VARCHAR(50);

-- 1.3 Tabla: trading_signals
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS rule_code           VARCHAR(10);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS signal_bar_index    BIGINT;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS signal_age_bars     SMALLINT DEFAULT 0;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS expires_at_bar      BIGINT;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS is_expired          BOOLEAN DEFAULT false;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ema20_phase         VARCHAR(20);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ema20_angle_raw     NUMERIC(8,4);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS adx_value           NUMERIC(6,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS plus_di             NUMERIC(6,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS minus_di            NUMERIC(6,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS confluence_score    SMALLINT;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS basis_15m           NUMERIC(20,8);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS basis_4h            NUMERIC(20,8);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS basis_1d            NUMERIC(20,8);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS fibonacci_zone      SMALLINT;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS regime              VARCHAR(20);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS risk_score          NUMERIC(5,1);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS mtf_score           NUMERIC(4,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS rr_real             NUMERIC(6,3);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_pattern          VARCHAR(50);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_sentiment        VARCHAR(20);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_recommendation   VARCHAR(10);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_agreed           BOOLEAN;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS ai_confidence       NUMERIC(4,2);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS acted_upon          BOOLEAN DEFAULT false;
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS blocked_reason      VARCHAR(100);
ALTER TABLE trading_signals ADD COLUMN IF NOT EXISTS is_paper            BOOLEAN DEFAULT false;

-- 1.4 Tabla: technical_indicators
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_phase         VARCHAR(20);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_angle_raw     NUMERIC(8,4);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_angle_pct     NUMERIC(5,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_was_flat      BOOLEAN;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_exit_flat_long  BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS ema20_exit_flat_short BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS adx                 NUMERIC(6,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS plus_di             NUMERIC(6,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS minus_di            NUMERIC(6,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS di_cross_bullish    BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS di_cross_bearish    BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS adx_rising          BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS basis_15m           NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS basis_4h            NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS basis_1d            NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS confluence_score    SMALLINT;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_ema             NUMERIC(20,2);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_slope_3         NUMERIC(8,4);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_decreasing      BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_increasing      BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS vol_entry_ok        BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS fibonacci_zone      SMALLINT;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS basis_vwma          NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_1             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_2             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_3             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_4             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_5             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS upper_6             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_1             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_2             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_3             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_4             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_5             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS lower_6             NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS atr                 NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS atr_percentile      NUMERIC(5,1);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_value          NUMERIC(20,8);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_4c_type        SMALLINT;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_buy            BOOLEAN DEFAULT false;
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS macd_sell           BOOLEAN DEFAULT false;

-- 1.5 Tabla: market_candles
ALTER TABLE market_candles ADD COLUMN IF NOT EXISTS timeframe       VARCHAR(5);
ALTER TABLE market_candles ADD COLUMN IF NOT EXISTS is_closed       BOOLEAN DEFAULT true;
ALTER TABLE market_candles ADD COLUMN IF NOT EXISTS hlc3            NUMERIC(20,8);
CREATE INDEX IF NOT EXISTS idx_market_candles_timeframe_ts ON market_candles(timeframe, open_time DESC);
CREATE INDEX IF NOT EXISTS idx_market_candles_symbol_tf ON market_candles(symbol, timeframe, open_time DESC);

-- 1.6 Tabla: risk_config
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS flat_pct              NUMERIC(5,2);
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS peak_pct              NUMERIC(5,2);
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS di_cross_required     BOOLEAN DEFAULT true;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS min_nivel_entrada     SMALLINT DEFAULT 1;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_daily_loss_pct    NUMERIC(5,2) DEFAULT 5.0;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_trade_loss_pct    NUMERIC(5,2) DEFAULT 2.0;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS post_sl_bars          SMALLINT DEFAULT 3;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS post_tp_bars          SMALLINT DEFAULT 1;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_correlation       NUMERIC(4,2) DEFAULT 0.80;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS vol_entry_min_pct     NUMERIC(5,2) DEFAULT 70.0;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS order_type_default    VARCHAR(10)  DEFAULT 'LIMIT';
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS limit_timeout_bars    SMALLINT DEFAULT 2;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS stop_limit_gap_pct    NUMERIC(5,3) DEFAULT 0.10;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS fee_pct               NUMERIC(5,4) DEFAULT 0.001;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS emergency_enabled     BOOLEAN DEFAULT true;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS emergency_atr_mult    NUMERIC(4,2) DEFAULT 2.0;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS emergency_action      VARCHAR(20)  DEFAULT 'pause';
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS signal_max_age_bars   SMALLINT DEFAULT 3;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS ai_candles_enabled    BOOLEAN DEFAULT true;
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS ai_candles_mode       VARCHAR(15) DEFAULT 'informative';
ALTER TABLE risk_config ADD COLUMN IF NOT EXISTS max_holding_bars      JSONB DEFAULT '{"5m":96,"15m":48,"30m":48,"45m":32,"4h":30,"1d":14,"1w":8}'::jsonb;

-- 1.7 Tabla: trading_config
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS capital_total          NUMERIC(12,2) DEFAULT 500.00;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS pct_for_trading        NUMERIC(5,2)  DEFAULT 20.0;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS capital_operativo      NUMERIC(12,2);
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS buffer_pct             NUMERIC(5,2)  DEFAULT 10.0;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS trade_distribution     JSONB DEFAULT '{"3_trades":{"t1":20,"t2":30,"t3":50},"5_trades":{"t1":10,"t2":15,"t3":20,"t4":25,"t5":30}}'::jsonb;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS market_type            VARCHAR(20)   DEFAULT 'futures';
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS leverage               SMALLINT      DEFAULT 5;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS active_symbols         JSONB         DEFAULT '["BTCUSDT","ETHUSDT","SOLUSDT","ADAUSDT"]'::jsonb;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS mode                   VARCHAR(10)   DEFAULT 'paper';
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS retention_days         JSONB DEFAULT '{"5m":20,"15m":60,"30m":90,"45m":120,"4h":365,"1d":1095,"1w":2190}'::jsonb;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS telegram_enabled       BOOLEAN DEFAULT true;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS telegram_bot_token     TEXT;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS telegram_chat_id       TEXT;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS warmup_bars_required   INT DEFAULT 200;
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS max_trade_loss_pct     NUMERIC(5,2)  DEFAULT 2.0;

-- 1.8 Tabla: paper_trades
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS rule_code           VARCHAR(10);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS regime              VARCHAR(20);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS risk_score          NUMERIC(5,1);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS ema20_phase         VARCHAR(20);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS adx_value           NUMERIC(6,2);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS confluence_score    SMALLINT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS signal_price        NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS execution_price     NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS slippage_pct        NUMERIC(8,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS ai_recommendation   VARCHAR(10);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS ai_agreed           BOOLEAN;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS ai_pattern          VARCHAR(50);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS bars_held           INT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS close_reason        VARCHAR(50);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS avg_entry_price     NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS entries             JSONB DEFAULT '[]'::jsonb;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS partial_pnl_usd     NUMERIC(10,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS full_pnl_usd        NUMERIC(10,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS total_pnl_usd       NUMERIC(10,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS total_pnl_pct       NUMERIC(8,4);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS basis_15m           NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS basis_4h            NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS basis_1d            NUMERIC(20,8);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS fibonacci_zone_entry SMALLINT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS market_type         VARCHAR(20);
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS leverage            SMALLINT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS liquidation_price   NUMERIC(20,8);

-- 1.9 Tabla: trading_rules
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS id                  BIGINT;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS rule_code           VARCHAR(10);
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS name                TEXT;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS description         TEXT;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS direction           VARCHAR(10);
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS market_type         JSONB;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS ema50_vs_ema200     VARCHAR(10);
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS enabled             BOOLEAN DEFAULT true;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS regime_allowed      JSONB;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS priority            INT DEFAULT 99;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS confidence          VARCHAR(10);
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS entry_trades        JSONB;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS conditions          JSONB;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS logic               VARCHAR(5) DEFAULT 'AND';
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS notes               TEXT;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS version             INT DEFAULT 1;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS current             BOOLEAN DEFAULT true;
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS created_at          TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE trading_rules ADD COLUMN IF NOT EXISTS updated_at          TIMESTAMPTZ DEFAULT NOW();
CREATE INDEX IF NOT EXISTS idx_trading_rules_active ON trading_rules(direction, enabled, current) WHERE enabled = true AND current = true;

-- 1.10 Tabla: market_regime
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS risk_score          NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS atr_percentile      NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS adx_value           NUMERIC(6,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS adx_risk_score      NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS volume_ratio        NUMERIC(6,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS volume_risk_score   NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS macro_trend         VARCHAR(10);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS macro_score         NUMERIC(5,1);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS mtf_threshold       NUMERIC(4,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS max_trades          SMALLINT;
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS emergency_active    BOOLEAN DEFAULT false;
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS emergency_atr_ratio NUMERIC(5,2);
ALTER TABLE market_regime ADD COLUMN IF NOT EXISTS evaluated_at        TIMESTAMPTZ DEFAULT NOW();

-- 1.11 Tabla: alert_events
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS alert_type     VARCHAR(30);
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS symbol         VARCHAR(20);
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS timeframe      VARCHAR(5);
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS severity       VARCHAR(10);
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS telegram_sent  BOOLEAN DEFAULT false;
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS resolved       BOOLEAN DEFAULT false;
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS resolved_at    TIMESTAMPTZ;
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS metadata       JSONB;

-- 1.12 Tabla: bot_state
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS warmup_completed       BOOLEAN DEFAULT false;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS warmup_bars_loaded     INT DEFAULT 0;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS warmup_bars_required   INT DEFAULT 200;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS last_15m_cycle_at      TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS last_5m_cycle_at       TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS last_reconcile_at      TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS last_cleanup_at        TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS circuit_breaker_active BOOLEAN DEFAULT false;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS circuit_breaker_since  TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS daily_pnl_usd          NUMERIC(10,4) DEFAULT 0;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS daily_pnl_reset_at     TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS emergency_active       BOOLEAN DEFAULT false;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS emergency_since        TIMESTAMPTZ;
ALTER TABLE bot_state ADD COLUMN IF NOT EXISTS mode                   VARCHAR(10) DEFAULT 'paper';


-- ==========================================================
-- PARTE 2: TABLAS NUEVAS
-- ==========================================================

CREATE TABLE IF NOT EXISTS reconciliation_log (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              VARCHAR(20)     NOT NULL,
    timeframe           VARCHAR(5),
    checked_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    bot_state           JSONB,
    exchange_state      JSONB,
    discrepancy_type    VARCHAR(50),
    action_taken        VARCHAR(100),
    supabase_updated    BOOLEAN DEFAULT false,
    telegram_notified   BOOLEAN DEFAULT false,
    resolved            BOOLEAN DEFAULT false,
    resolved_at         TIMESTAMPTZ,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS symbol_health_checks (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              VARCHAR(20)     NOT NULL,
    market_type         VARCHAR(20),
    checked_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    volume_24h          NUMERIC(20,2),
    spread_pct          NUMERIC(8,4),
    best_bid            NUMERIC(20,8),
    best_ask            NUMERIC(20,8),
    volume_ok           BOOLEAN,
    spread_ok           BOOLEAN,
    symbol_active       BOOLEAN,
    healthy             BOOLEAN,
    min_volume_usd      NUMERIC(20,2),
    max_spread_pct      NUMERIC(5,3),
    blocked_entry       BOOLEAN DEFAULT false,
    block_reason        TEXT
);

CREATE TABLE IF NOT EXISTS funding_rates (
    id                      BIGSERIAL PRIMARY KEY,
    symbol                  VARCHAR(20)     NOT NULL,
    rate                    NUMERIC(12,8)   NOT NULL,
    next_funding_time       TIMESTAMPTZ,
    checked_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    projected_cost_24h_pct  NUMERIC(10,6),
    projected_cost_24h_usd  NUMERIC(10,4),
    favorable_for_long      BOOLEAN,
    favorable_for_short     BOOLEAN,
    position_id             UUID REFERENCES positions(id) ON DELETE SET NULL,
    accrued_cost_usd        NUMERIC(10,4) DEFAULT 0,
    payments_count          SMALLINT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS slippage_log (
    id                  BIGSERIAL PRIMARY KEY,
    order_id            UUID REFERENCES orders(id) ON DELETE CASCADE,
    symbol              VARCHAR(20)     NOT NULL,
    market_type         VARCHAR(20),
    order_type          VARCHAR(10),
    side                VARCHAR(10),
    signal_price        NUMERIC(20,8)   NOT NULL,
    execution_price     NUMERIC(20,8)   NOT NULL,
    slippage_pct        NUMERIC(8,4)    NOT NULL,
    slippage_usd        NUMERIC(10,4),
    is_paper            BOOLEAN DEFAULT false,
    timestamp           TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE VIEW slippage_summary AS
SELECT
    symbol,
    order_type,
    COUNT(*)                        AS total_orders,
    ROUND(AVG(slippage_pct), 4)    AS avg_slippage_pct,
    ROUND(MAX(slippage_pct), 4)    AS max_slippage_pct,
    ROUND(SUM(slippage_usd), 2)    AS total_slippage_usd
FROM slippage_log
WHERE timestamp >= NOW() - INTERVAL '30 days'
GROUP BY symbol, order_type
ORDER BY avg_slippage_pct DESC;


-- ==========================================================
-- PARTE 3: SEED (TRADING RULES)
-- ==========================================================

INSERT INTO trading_rules
  (id, rule_code, name, description, direction, market_type, ema50_vs_ema200,
   enabled, regime_allowed, priority, confidence, entry_trades, conditions, logic, notes, version, current, created_at, updated_at)
VALUES
(1001, 'Aa13', 'LONG — EMA50 cruza basis (macro bajista)', 'EMA50 supera la VWMA (basis) en mercado macro bajista. Señal de cambio de tendencia local.', 'long', '["crypto_spot","crypto_futures"]', 'below', true, '["riesgo_medio","bajo_riesgo"]', 1, 'high', '[1]', '[{"indicator":"ema4_cross_basis_up","operator":"==","value":true},{"indicator":"pinescript_signal","operator":"==","value":"Buy"}]', 'AND', 'Al momento del cruce, comprar al primer Buy del PineScript', 1, true, NOW(), NOW()),
(1002, 'Aa12', 'LONG — Rebote desde lower_5/6 (macro bajista)', 'Precio tocó lower_5 o lower_6 con EMA20 girando positivo. Rebote desde sobreventa extrema.', 'long', '["crypto_spot","crypto_futures"]', 'below', true, '["riesgo_medio","bajo_riesgo"]', 2, 'medium', '[1]', '[{"indicator":"ema20_angle_raw","operator":">=","value":0},{"indicator":"low_crossed_lower5_or_6","operator":"==","value":true},{"indicator":"reversal_confirmed","operator":"==","value":true}]', 'AND', 'Confirmación: is_dragonfly OR low_higher_than_prev', 1, true, NOW(), NOW()),
(1003, 'Aa11', 'LONG — EMA20 flat + ADX bajo + DI cruce (macro bajista)', 'Acumulación temprana. EMA20 positivo con ADX bajo y cruce alcista del DI.', 'long', '["crypto_spot","crypto_futures"]', 'below', true, '["riesgo_medio","bajo_riesgo"]', 3, 'medium', '[1]', '[{"indicator":"ema20_angle_raw","operator":">=","value":0},{"indicator":"adx","operator":"<","value":20},{"indicator":"ema20_phase","operator":"==","value":"nivel_1_long"},{"indicator":"di_cross_bullish","operator":"==","value":true}]', 'AND', 'Solo régimen riesgo_medio o bajo_riesgo. Solo T1.', 1, true, NOW(), NOW()),
(1004, 'Aa24', 'LONG — EMA50 cruza basis + Nivel 1 (macro alcista)', 'EMA50 supera el basis VWMA con EMA20 en fase nivel_1_long. Entrada de alta confianza.', 'long', '["crypto_spot","crypto_futures"]', 'above', true, '["alto_riesgo","riesgo_medio","bajo_riesgo"]', 1, 'high', '[1,2,3]', '[{"indicator":"ema4_cross_basis_up","operator":"==","value":true},{"indicator":"ema20_phase","operator":"==","value":"nivel_1_long"},{"indicator":"pinescript_signal","operator":"==","value":"Buy"}]', 'AND', 'Habilitar T2/T3 con condición precio decreciente', 1, true, NOW(), NOW()),
(1005, 'Aa22', 'LONG — EMA50 ascendente sobre basis (macro alcista)', 'EMA50 ángulo positivo Y precio del EMA50 sobre el basis VWMA.', 'long', '["crypto_spot","crypto_futures"]', 'above', true, '["alto_riesgo","riesgo_medio","bajo_riesgo"]', 2, 'high', '[1]', '[{"indicator":"ema50_angle","operator":">=","value":0},{"indicator":"ema4_above_basis","operator":"==","value":true}]', 'AND', NULL, 1, true, NOW(), NOW()),
(1006, 'Aa23', 'LONG — EMA9 + EMA50 ascendentes (macro alcista)', 'Ambas EMAs dinámicas apuntan hacia arriba. Momentum de corto y mediano plazo alineados.', 'long', '["crypto_spot","crypto_futures"]', 'above', true, '["riesgo_medio","bajo_riesgo"]', 3, 'medium', '[1]', '[{"indicator":"ema9_angle","operator":">=","value":0},{"indicator":"ema50_angle","operator":">=","value":0},{"indicator":"adx","operator":">=","value":"adx_min_config"}]', 'AND', 'adx_min_config viene del régimen activo', 1, true, NOW(), NOW()),
(1007, 'Aa21', 'LONG — EMA20 flat + ADX bajo cerca del basis (macro alcista)', 'Señal temprana en lateral. Solo válida muy cerca del basis.', 'long', '["crypto_spot","crypto_futures"]', 'above', true, '["bajo_riesgo"]', 4, 'low', '[1]', '[{"indicator":"ema20_angle_raw","operator":">=","value":0},{"indicator":"adx","operator":"<","value":20},{"indicator":"fibonacci_zone","operator":"between","value":[-2,2]},{"indicator":"close_vs_basis","operator":"<=","value":1.005}]', 'AND', 'Solo régimen bajo_riesgo. Solo T1.', 1, true, NOW(), NOW()),
(1008, 'Bb12', 'SHORT — EMA50 cruza basis hacia abajo (macro bajista)', 'EMA50 perfora el basis VWMA en mercado macro bajista. Señal de continuación bajista.', 'short', '["crypto_spot","crypto_futures"]', 'below', true, '["alto_riesgo","riesgo_medio","bajo_riesgo"]', 1, 'high', '[1]', '[{"indicator":"ema4_cross_basis_down","operator":"==","value":true},{"indicator":"pinescript_signal","operator":"==","value":"Sell"}]', 'AND', 'Al momento del cruce, abrir SHORT al primer Sell del PineScript', 1, true, NOW(), NOW()),
(1009, 'Bb13', 'SHORT — EMA50 bajo basis + ADX + DI cruce (macro bajista)', 'Distribución temprana en consolidación. EMA50 ya bajo el basis con cruce bajista del DI.', 'short', '["crypto_spot","crypto_futures"]', 'below', true, '["riesgo_medio","bajo_riesgo"]', 2, 'high', '[1]', '[{"indicator":"ema4_below_basis","operator":"==","value":true},{"indicator":"adx","operator":"<","value":20},{"indicator":"ema20_phase","operator":"in","value":["flat","nivel_1_short"]},{"indicator":"di_cross_bearish","operator":"==","value":true},{"indicator":"ema20_angle_raw","operator":"<=","value":0}]', 'AND', NULL, 1, true, NOW(), NOW()),
(1010, 'Bb11', 'SHORT — ADX fuerte + Nivel 2 bajista (macro bajista)', 'Impulso bajista fuerte confirmado con ADX > 40 y fase nivel_2_short.', 'short', '["crypto_spot","crypto_futures"]', 'below', true, '["riesgo_medio","bajo_riesgo"]', 3, 'medium', '[1,2]', '[{"indicator":"ema20_angle_raw","operator":"<=","value":0},{"indicator":"adx","operator":">","value":40},{"indicator":"ema20_phase","operator":"==","value":"nivel_2_short"},{"indicator":"di_spread","operator":">=","value":5}]', 'AND', 'di_spread = minus_di - plus_di >= 5 puntos', 1, true, NOW(), NOW()),
(1011, 'Bb22', 'SHORT — Agotamiento extremo en upper_6 (macro alcista)', 'HIGH cruzó upper_6 con ADX fuerte y EMA50 girando negativo. Reversal técnico en extremo Fibonacci.', 'short', '["crypto_spot","crypto_futures"]', 'above', true, '["riesgo_medio","bajo_riesgo"]', 1, 'high', '[1]', '[{"indicator":"high_crossed_upper6","operator":"==","value":true},{"indicator":"adx","operator":">","value":40},{"indicator":"ema20_phase","operator":"==","value":"nivel_2_long"},{"indicator":"ema50_angle","operator":"<=","value":0},{"indicator":"reversal_candle_bearish","operator":"==","value":true}]', 'AND', 'reversal_candle_bearish = is_gravestone OR (is_red_candle AND high_in_upper6) OR high_lower_than_prev. RR mínimo forzado 3.0. Solo T1.', 1, true, NOW(), NOW()),
(1012, 'Bb23', 'SHORT — EMA50 cruza basis + EMA20 negativo (macro alcista)', 'EMA50 perfora el basis con EMA20 ya negativo. Señal más limpia de cambio en macro alcista.', 'short', '["crypto_spot","crypto_futures"]', 'above', true, '["riesgo_medio","bajo_riesgo"]', 2, 'high', '[1]', '[{"indicator":"ema4_cross_basis_down","operator":"==","value":true},{"indicator":"ema20_angle_raw","operator":"<=","value":0},{"indicator":"pinescript_signal","operator":"==","value":"Sell"}]', 'AND', 'Al momento del cruce. RR mínimo del régimen activo.', 1, true, NOW(), NOW()),
(1013, 'Bb21', 'SHORT — ADX fuerte + Nivel 2 bajista (macro alcista)', 'Impulso bajista fuerte en mercado macro alcista. Alta selectividad.', 'short', '["crypto_spot","crypto_futures"]', 'above', true, '["bajo_riesgo"]', 3, 'medium', '[1]', '[{"indicator":"ema20_angle_raw","operator":"<=","value":0},{"indicator":"adx","operator":">","value":40},{"indicator":"ema20_phase","operator":"==","value":"nivel_2_short"},{"indicator":"di_spread","operator":">=","value":10}]', 'AND', 'di_spread = minus_di - plus_di >= 10 puntos. Solo bajo_riesgo. RR mínimo 3.0. Solo T1.', 1, true, NOW(), NOW())
ON CONFLICT (id) DO UPDATE SET
    rule_code       = EXCLUDED.rule_code,
    name            = EXCLUDED.name,
    description     = EXCLUDED.description,
    conditions      = EXCLUDED.conditions,
    regime_allowed  = EXCLUDED.regime_allowed,
    confidence      = EXCLUDED.confidence,
    notes           = EXCLUDED.notes,
    version         = trading_rules.version + 1,
    updated_at      = NOW()
WHERE trading_rules.conditions != EXCLUDED.conditions;


-- ==========================================================
-- PARTE 4: ÍNDICES DE PERFORMANCE
-- ==========================================================

CREATE INDEX IF NOT EXISTS idx_reconciliation_symbol ON reconciliation_log(symbol, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_reconciliation_unresolved ON reconciliation_log(resolved, checked_at DESC) WHERE resolved = false;
CREATE INDEX IF NOT EXISTS idx_health_checks_symbol ON symbol_health_checks(symbol, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_health_checks_cleanup ON symbol_health_checks(checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol ON funding_rates(symbol, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_funding_rates_symbol_time ON funding_rates(symbol, next_funding_time);
CREATE INDEX IF NOT EXISTS idx_slippage_symbol ON slippage_log(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_slippage_order_type ON slippage_log(order_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_technical_indicators_symbol_tf ON technical_indicators(symbol, timeframe, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(symbol, status) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS idx_trading_signals_active ON trading_signals(symbol, is_expired, acted_upon, created_at DESC) WHERE is_expired = false AND acted_upon = false;
CREATE INDEX IF NOT EXISTS idx_cooldowns_active ON cooldowns(symbol, active, expires_at) WHERE active = true;
CREATE INDEX IF NOT EXISTS idx_orders_pending ON orders(symbol, status, created_at DESC) WHERE status IN ('pending', 'partially_filled');
CREATE INDEX IF NOT EXISTS idx_funding_rates_latest ON funding_rates(symbol, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_trades_analysis ON paper_trades(rule_code, regime, close_reason, created_at DESC);

-- <<< migration_010_sprint1_master_schema.sql <<<


-- >>> migration_011_pilot_diagnostics_fix.sql >>>
-- ═══════════════════════════════════════════════════════
-- MIGRACIÓN 011: pilot_diagnostics — Columnas Maestras para v4
-- eTrade v3 | Marzo 2026
-- ═══════════════════════════════════════════════════════

-- 1. Agregar columnas faltantes (Idempotente)
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS symbol               VARCHAR(20);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS cycle_type           VARCHAR(10);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS risk_category        VARCHAR(20);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS risk_score           NUMERIC(5,1);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS ema20_phase          VARCHAR(20);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS ema20_angle_raw      NUMERIC(8,4);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS adx_value            NUMERIC(6,2);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS macd_4c_type         SMALLINT;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS fibonacci_zone       SMALLINT;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS confluence_score     SMALLINT;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS mtf_score            NUMERIC(4,2);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS pinescript_signal    VARCHAR(10);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS signal_age_bars      SMALLINT;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS rule_evaluated       VARCHAR(10);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS rule_triggered       BOOLEAN DEFAULT false;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS entry_blocked_by     VARCHAR(100);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS current_price        NUMERIC(20,8);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS basis_15m            NUMERIC(20,8);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS basis_4h             NUMERIC(20,8);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS basis_1d             NUMERIC(20,8);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS upper_5              NUMERIC(20,8);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS upper_6              NUMERIC(20,8);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS lower_5              NUMERIC(20,8);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS lower_6              NUMERIC(20,8);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS regime_changed       BOOLEAN DEFAULT false;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS emergency_active     BOOLEAN DEFAULT false;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS circuit_breaker      BOOLEAN DEFAULT false;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS cooldown_active      BOOLEAN DEFAULT false;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS ai_pattern           VARCHAR(50);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS ai_recommendation    VARCHAR(10);
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS ai_agreed            BOOLEAN;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS cycle_duration_ms    INT;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS error_occurred       BOOLEAN DEFAULT false;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS error_message        TEXT;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS raw_indicators       JSONB;
ALTER TABLE pilot_diagnostics ADD COLUMN IF NOT EXISTS timestamp            TIMESTAMPTZ DEFAULT NOW();

-- 2. Índices para consultas de diagnóstico
CREATE INDEX IF NOT EXISTS idx_pilot_diagnostics_symbol_ts
    ON pilot_diagnostics(symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_pilot_diagnostics_rule
    ON pilot_diagnostics(rule_evaluated, rule_triggered, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_pilot_diagnostics_errors
    ON pilot_diagnostics(error_occurred, timestamp DESC)
    WHERE error_occurred = true;

-- 3. Verificación rápida
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'pilot_diagnostics'
  AND column_name IN (
    'symbol', 'cycle_type', 'risk_category', 'ema20_phase',
    'rule_evaluated', 'rule_triggered', 'entry_blocked_by',
    'cycle_duration_ms', 'timestamp'
  )
ORDER BY column_name;

-- <<< migration_011_pilot_diagnostics_fix.sql <<<


-- >>> migration_013_parameter_bounds.sql >>>
-- migration_013_parameter_bounds.sql
-- Sistema de Guardrails de Parámetros para eTrade v3

-- Tabla de límites por parámetro
CREATE TABLE IF NOT EXISTS parameter_bounds (
    parameter_name      VARCHAR(50)  PRIMARY KEY,
    category            VARCHAR(20)  NOT NULL,
    -- Valores: 'risk' | 'entry' | 'sizing' | 'timing' | 'technical'

    min_value           NUMERIC(10,4) NOT NULL,
    max_value           NUMERIC(10,4) NOT NULL,
    default_value       NUMERIC(10,4) NOT NULL,
    current_value       NUMERIC(10,4) NOT NULL,

    description         TEXT,
    unit                VARCHAR(20),    -- 'ratio' | 'multiplier' | 'pct' | 'bars' | 'float'
    regime              VARCHAR(20),    -- 'bajo_riesgo' | 'riesgo_medio' | 'alto_riesgo' | 'all'

    requires_approval_outside_bounds  BOOLEAN DEFAULT true,
    last_changed_at     TIMESTAMPTZ DEFAULT NOW(),
    last_changed_by     VARCHAR(50),    -- 'system' | 'antigravity' | 'jhon'
    change_reason       TEXT,

    -- Performance al momento del último cambio
    perf_win_rate_before    NUMERIC(5,4),
    perf_win_rate_after     NUMERIC(5,4),
    perf_ev_before          NUMERIC(8,4),   -- expected value antes del cambio
    perf_ev_after           NUMERIC(8,4),   -- expected value después del cambio

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Historial de todos los cambios (audit trail)
CREATE TABLE IF NOT EXISTS parameter_changes_log (
    id              BIGSERIAL PRIMARY KEY,
    parameter_name  VARCHAR(50) REFERENCES parameter_bounds(parameter_name),
    old_value       NUMERIC(10,4),
    new_value       NUMERIC(10,4),
    changed_at      TIMESTAMPTZ DEFAULT NOW(),
    changed_by      VARCHAR(50),
    change_reason   TEXT,
    within_bounds   BOOLEAN,
    approved_by     VARCHAR(50),    -- null si dentro de bounds, 'jhon' si fuera
    backtest_ev     NUMERIC(8,4),   -- expected value del backtest que justificó el cambio
    accepted        BOOLEAN
);

-- SEED INICIAL 
INSERT INTO parameter_bounds
    (parameter_name, category, min_value, max_value, default_value, current_value,
     description, unit, regime)
VALUES

-- ═══ PARÁMETROS DE RIESGO (RR mínimo) ═══
('rr_min_bajo_riesgo',     'risk', 1.5, 4.0, 2.0, 2.0,
 'RR mínimo aceptable en régimen bajo riesgo. < 1.5 destruye esperanza matemática con 50% win rate.',
 'ratio', 'bajo_riesgo'),

('rr_min_riesgo_medio',    'risk', 1.5, 4.0, 2.5, 2.5,
 'RR mínimo aceptable en régimen riesgo medio. Mayor que bajo_riesgo para compensar el mayor ATR.',
 'ratio', 'riesgo_medio'),

('rr_min_alto_riesgo',     'risk', 2.0, 4.0, 3.0, 3.0,
 'RR mínimo aceptable en régimen alto riesgo. El más exigente por la mayor volatilidad.',
 'ratio', 'alto_riesgo'),

-- ═══ PARÁMETROS DE RIESGO (SL — multiplicador ATR) ═══
('atr_mult_bajo_riesgo',   'risk', 1.0, 3.5, 1.5, 1.5,
 'Multiplicador del ATR para calcular el Stop Loss en bajo riesgo. SL = entry - (ATR × mult).',
 'multiplier', 'bajo_riesgo'),

('atr_mult_riesgo_medio',  'risk', 1.0, 3.5, 2.0, 2.0,
 'Multiplicador del ATR para calcular el Stop Loss en riesgo medio.',
 'multiplier', 'riesgo_medio'),

('atr_mult_alto_riesgo',   'risk', 1.0, 3.5, 2.5, 2.5,
 'Multiplicador del ATR para calcular el Stop Loss en alto riesgo.',
 'multiplier', 'alto_riesgo'),

-- ═══ PARÁMETROS DE ENTRADA (MTF threshold) ═══
('mtf_threshold_bajo',     'entry', 0.45, 0.90, 0.50, 0.50,
 'Umbral de alineación multi-timeframe en bajo riesgo. Al menos 50% de TFs alineados.',
 'pct', 'bajo_riesgo'),

('mtf_threshold_medio',    'entry', 0.45, 0.90, 0.65, 0.65,
 'Umbral de alineación multi-timeframe en riesgo medio. Al menos 65% de TFs alineados.',
 'pct', 'riesgo_medio'),

('mtf_threshold_alto',     'entry', 0.45, 0.90, 0.80, 0.80,
 'Umbral de alineación multi-timeframe en alto riesgo. Al menos 80% de TFs alineados.',
 'pct', 'alto_riesgo'),

-- ═══ PARÁMETROS TÉCNICOS (EMA20 phases) ═══
('ema20_flat_pct_bajo',    'technical', 10.0, 30.0, 15.0, 15.0,
 'Percentil que define zona plana del EMA20 en bajo riesgo.',
 'pct', 'bajo_riesgo'),

('ema20_flat_pct_medio',   'technical', 10.0, 30.0, 20.0, 20.0,
 'Percentil que define zona plana del EMA20 en riesgo medio.',
 'pct', 'riesgo_medio'),

('ema20_flat_pct_alto',    'technical', 10.0, 30.0, 25.0, 25.0,
 'Percentil que define zona plana del EMA20 en alto riesgo.',
 'pct', 'alto_riesgo'),

('ema20_peak_pct_bajo',    'technical', 70.0, 90.0, 85.0, 85.0,
 'Percentil que define zona de cima del EMA20 en bajo riesgo.',
 'pct', 'bajo_riesgo'),

('ema20_peak_pct_medio',   'technical', 70.0, 90.0, 80.0, 80.0,
 'Percentil que define zona de cima del EMA20 en riesgo medio.',
 'pct', 'riesgo_medio'),

('ema20_peak_pct_alto',    'technical', 70.0, 90.0, 75.0, 75.0,
 'Percentil que define zona de cima del EMA20 en alto riesgo.',
 'pct', 'alto_riesgo'),

-- ═══ PARÁMETROS DE TIMING (cooldown y holding) ═══
('post_sl_cooldown_bars',  'timing', 1, 10, 3, 3,
 'Velas de cooldown después de un SL. Evita revenge trading automático.',
 'bars', 'all'),

('post_tp_cooldown_bars',  'timing', 0, 5,  1, 1,
 'Velas de cooldown después de un TP.',
 'bars', 'all'),

('signal_max_age_bars',    'timing', 1, 10, 3, 3,
 'Máximo de barras que puede tener una señal del PineScript antes de expirar.',
 'bars', 'all'),

-- ═══ PARÁMETROS DE SIZING ═══
('capital_pct_for_trading','sizing', 5.0, 50.0, 20.0, 20.0,
 '% del capital total destinado a trading. El 80% restante permanece como reserva.',
 'pct', 'all'),

('fee_pct',                'sizing', 0.001, 0.002, 0.001, 0.001,
 'Fee estimado de Binance por operación (0.1% maker/taker).',
 'float', 'all'),

-- ═══ PROTECCIONES DE RIESGO ═══
('max_daily_loss_pct',     'risk', 2.0, 15.0, 5.0, 5.0,
 '% máximo de pérdida diaria sobre capital total antes de activar circuit breaker.',
 'pct', 'all'),

('max_trade_loss_pct',     'risk', 0.5, 5.0, 2.0, 2.0,
 '% máximo de pérdida por trade individual sobre capital total.',
 'pct', 'all'),

('emergency_atr_mult',     'risk', 1.5, 4.0, 2.0, 2.0,
 'Multiplicador del ATR promedio que activa el monitor de emergencia vía WebSocket.',
 'multiplier', 'all')

ON CONFLICT (parameter_name) DO NOTHING;

-- <<< migration_013_parameter_bounds.sql <<<


-- >>> migration_014_signals_log.sql >>>
-- MIGRATION 014: signals_log — Auditoría de señales detectadas (Ejecutadas y Bloqueadas)
-- eTrade v4 | Marzo 2026

CREATE TABLE IF NOT EXISTS signals_log (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(30) NOT NULL,
    direction       VARCHAR(10) NOT NULL,
    rule_code       VARCHAR(10),
    price           NUMERIC(20,8),
    score_final     NUMERIC(8,4),
    acted_on        BOOLEAN DEFAULT false,
    reason_skip     TEXT,
    metadata        JSONB,
    detected_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_log_symbol_ts ON signals_log(symbol, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_log_acted_on ON signals_log(acted_on, detected_at DESC);

-- Habilitar tiempo real
-- ALTER PUBLICATION supabase_realtime ADD TABLE signals_log;

-- <<< migration_014_signals_log.sql <<<


-- >>> migration_015_market_snapshot.sql >>>
CREATE TABLE IF NOT EXISTS market_snapshot (
    symbol           VARCHAR(20)  PRIMARY KEY,
    price            NUMERIC(20,8),
    fibonacci_zone   SMALLINT,
    basis            NUMERIC(20,8),
    upper_5          NUMERIC(20,8),
    upper_6          NUMERIC(20,8),
    lower_5          NUMERIC(20,8),
    lower_6          NUMERIC(20,8),
    dist_basis_pct   NUMERIC(8,4),
    mtf_score        NUMERIC(5,4),
    ema20_phase      VARCHAR(20),
    adx              NUMERIC(8,4),
    regime           VARCHAR(20),
    risk_score       NUMERIC(5,1),
    spike_detected   BOOLEAN      DEFAULT false,
    spike_ratio      NUMERIC(8,4),
    spike_direction  VARCHAR(15),
    updated_at       TIMESTAMPTZ  DEFAULT NOW()
);

-- Habilitar Realtime para que el frontend reciba
-- actualizaciones instantáneas cada ciclo de 15m
ALTER PUBLICATION supabase_realtime
    ADD TABLE market_snapshot;

-- <<< migration_015_market_snapshot.sql <<<


-- >>> migration_016_exit_reversal.sql >>>
-- CAMBIO 2 - PASO 1: Agregar parmetros en trading_config
ALTER TABLE trading_config
ADD COLUMN IF NOT EXISTS exit_on_signal_reversal BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS exit_mtf_threshold NUMERIC(4,2) DEFAULT 0.00,
ADD COLUMN IF NOT EXISTS min_profit_exit_pct NUMERIC(5,2) DEFAULT 0.30,
ADD COLUMN IF NOT EXISTS min_profit_exit_usd NUMERIC(8,2) DEFAULT 1.00;

-- Asegurar valores iniciales para la config principal
UPDATE trading_config
SET
  exit_on_signal_reversal = true,
  exit_mtf_threshold      = 0.00,
  min_profit_exit_pct     = 0.30,
  min_profit_exit_usd     = 1.00
WHERE id = 1;

-- <<< migration_016_exit_reversal.sql <<<


-- >>> migration_017_market_snapshot_bands.sql >>>
-- Migration 017: Expand market_snapshot with full Fibonacci bands
-- Added upper_1..4 and lower_1..4 for dynamic TP logic

ALTER TABLE market_snapshot
ADD COLUMN IF NOT EXISTS upper_1 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS upper_2 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS upper_3 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS upper_4 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS lower_1 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS lower_2 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS lower_3 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS lower_4 NUMERIC(20,8);

-- <<< migration_017_market_snapshot_bands.sql <<<


-- >>> migration_018_sar_4h.sql >>>
-- MIGRATION 018 — Parabolic SAR 4h Filter
-- Adds SAR columns to market_snapshot for macro direction filtering

ALTER TABLE market_snapshot
ADD COLUMN IF NOT EXISTS
  sar_4h         NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS
  sar_trend_4h   SMALLINT DEFAULT 0,
ADD COLUMN IF NOT EXISTS
  sar_phase      VARCHAR(10) DEFAULT 'neutral',
ADD COLUMN IF NOT EXISTS
  sar_phase_changed_at TIMESTAMPTZ;

-- Index for performance on phase queries
CREATE INDEX IF NOT EXISTS idx_market_snapshot_sar_phase ON market_snapshot(sar_phase);

-- Step 2.1 — Add SAR to market_candles for chart visualization
ALTER TABLE market_candles
ADD COLUMN IF NOT EXISTS
  sar         NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS
  sar_trend   SMALLINT;

COMMENT ON COLUMN market_snapshot.sar_phase IS 'sar_phase valores: long, short, neutral';

-- <<< migration_018_sar_4h.sql <<<


-- >>> migration_019_sar_15m.sql >>>
-- migration_019_sar_15m.sql
ALTER TABLE market_snapshot
ADD COLUMN IF NOT EXISTS sar_15m       NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS sar_trend_15m SMALLINT DEFAULT 0,
ADD COLUMN IF NOT EXISTS sar_ini_high_15m BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS sar_ini_low_15m  BOOLEAN DEFAULT false;

INSERT INTO trading_rules (
    id, rule_code, name, direction,
    market_type, enabled, regime_allowed,
    priority, confidence, version
) VALUES
(1014, 'Cc21', 'LONG SAR scalp — SAR 15m + 4h + PineScript', 'long', 'futures', true, 'all', 1, 0.70, 1),
(1015, 'Cc11', 'SHORT SAR scalp — SAR 15m + 4h + PineScript', 'short', 'futures', true, 'all', 1, 0.70, 1)
ON CONFLICT (id) DO NOTHING;

-- <<< migration_019_sar_15m.sql <<<


-- >>> migration_020_pending_orders.sql >>>
CREATE TABLE IF NOT EXISTS pending_orders (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    exchange VARCHAR(50) DEFAULT 'binance',
    side VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) DEFAULT 'LIMIT',
    price NUMERIC(20,8) NOT NULL,
    size NUMERIC(20,8) NOT NULL,
    rule_code VARCHAR(20),
    status VARCHAR(20) DEFAULT 'pending', 
    external_order_id VARCHAR(100), 
    cycle_type VARCHAR(10), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    expires_at TIMESTAMP WITH TIME ZONE
);

-- <<< migration_020_pending_orders.sql <<<


-- >>> migration_021_pending_orders_v2.sql >>>
DROP TABLE IF EXISTS pending_orders;

CREATE TABLE IF NOT EXISTS pending_orders (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol        VARCHAR(20)    NOT NULL,
    direction     VARCHAR(10)    NOT NULL,
    order_type    VARCHAR(10)    DEFAULT 'limit',
    trade_type    VARCHAR(10)    DEFAULT 'swing',
    rule_code     VARCHAR(10),
    limit_price   NUMERIC(20,8),
    sl_price      NUMERIC(20,8),
    tp1_price     NUMERIC(20,8),
    tp2_price     NUMERIC(20,8),
    band_name     VARCHAR(20),
    basis_slope   NUMERIC(10,6), -- pendiente basis al crear
    status        VARCHAR(20)    DEFAULT 'pending',
    mode          VARCHAR(10)    DEFAULT 'paper',
    created_at    TIMESTAMPTZ    DEFAULT NOW(),
    updated_at    TIMESTAMPTZ    DEFAULT NOW(),
    triggered_at  TIMESTAMPTZ,
    cancelled_at  TIMESTAMPTZ,
    expires_at    TIMESTAMPTZ,   -- TTL opcional
    version       INTEGER        DEFAULT 1
);

-- Index para búsqueda rápida en ciclo de 5m
CREATE INDEX IF NOT EXISTS idx_pending_orders_symbol ON pending_orders(symbol, status);

-- <<< migration_021_pending_orders_v2.sql <<<


-- >>> migration_022_structure_confirmation.sql >>>
-- Migration 022: Market Structure Confirmation columns
-- Adds structure analysis results for 15m and 4h timeframes

ALTER TABLE market_snapshot
ADD COLUMN IF NOT EXISTS structure_15m        VARCHAR(20) DEFAULT 'unknown',
ADD COLUMN IF NOT EXISTS allow_long_15m       BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS allow_short_15m      BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS reverse_signal_15m   BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS structure_reason_15m TEXT,
ADD COLUMN IF NOT EXISTS structure_4h         VARCHAR(20) DEFAULT 'unknown',
ADD COLUMN IF NOT EXISTS allow_long_4h        BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS allow_short_4h       BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS reverse_signal_4h    BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS structure_reason_4h  TEXT;

-- <<< migration_022_structure_confirmation.sql <<<


-- >>> migration_023_strategy_engine_v1.sql >>>

-- TABLA 1: Variables del sistema
CREATE TABLE IF NOT EXISTS strategy_variables (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(50)  UNIQUE NOT NULL,
    category     VARCHAR(20)  NOT NULL,
    timeframes   TEXT[],
    data_type    VARCHAR(20),
    description  TEXT,
    source_field VARCHAR(100),
    enabled      BOOLEAN DEFAULT true,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- TABLA 2: Condiciones
CREATE TABLE IF NOT EXISTS strategy_conditions (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    variable_id    INTEGER REFERENCES strategy_variables(id),
    operator       VARCHAR(20)  NOT NULL,
    value_type     VARCHAR(20)  NOT NULL,
    value_literal  NUMERIC,
    value_variable VARCHAR(50),
    value_list     TEXT[],
    value_min      NUMERIC,
    value_max      NUMERIC,
    timeframe      VARCHAR(10),
    description    TEXT,
    enabled        BOOLEAN DEFAULT true,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- TABLA 3: Reglas v2
CREATE TABLE IF NOT EXISTS strategy_rules_v2 (
    id                  SERIAL PRIMARY KEY,
    rule_code           VARCHAR(20) UNIQUE NOT NULL,
    name                VARCHAR(200) NOT NULL,
    strategy_type       VARCHAR(20)  NOT NULL,
    direction           VARCHAR(10)  NOT NULL,
    cycle               VARCHAR(10)  NOT NULL,
    condition_ids       INTEGER[]    NOT NULL,
    condition_logic     TEXT         DEFAULT 'AND',
    min_score           NUMERIC      DEFAULT 0.60,
    condition_weights   JSONB,
    market_types        TEXT[]       DEFAULT '{crypto_futures}',
    enabled             BOOLEAN      DEFAULT true,
    priority            INTEGER      DEFAULT 1,
    confidence          NUMERIC      DEFAULT 0.70,
    version             INTEGER      DEFAULT 1,
    notes               TEXT,
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);

-- TABLA 4: Log de evaluaciones
CREATE TABLE IF NOT EXISTS strategy_evaluations (
    id          UUID    DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol      VARCHAR(20) NOT NULL,
    rule_code   VARCHAR(20) NOT NULL,
    cycle       VARCHAR(10),
    direction   VARCHAR(10),
    score       NUMERIC,
    triggered   BOOLEAN,
    context     JSONB,
    conditions  JSONB,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Index para búsquedas rápidas
CREATE INDEX IF NOT EXISTS idx_strat_eval_symbol ON strategy_evaluations(symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_strat_eval_triggered ON strategy_evaluations(triggered, created_at DESC);

-- INSERTAR VARIABLES
INSERT INTO strategy_variables (id, name, category, timeframes, data_type, description, source_field)
VALUES
(1,  'price',           'price',       '{5m,15m,4h}', 'float', 'Precio actual de mercado', 'price'),
(2,  'dist_basis_pct',  'price',       '{5m,15m,4h}', 'float', '% distancia desde el BASIS', 'dist_basis_pct'),
(3,  'adx',             'statistical', '{5m,15m,4h}', 'float', 'ADX (0-100)', 'adx'),
(4,  'adx_plus_di',     'statistical', '{5m,15m,4h}', 'float', '+DI presión compradora', 'plus_di'),
(5,  'adx_minus_di',    'statistical', '{5m,15m,4h}', 'float', '-DI presión vendedora', 'minus_di'),
(6,  'adx_velocity',    'system',      '{5m,15m,4h}', 'string', 'Velocidad mercado (debil/moderado/agresivo/explosivo)', 'adx_velocity'),
(7,  'ema3',            'ema',         '{5m,15m,4h}', 'float', 'EMA 3 períodos', 'ema3'),
(8,  'ema9',            'ema',         '{5m,15m,4h}', 'float', 'EMA 9 períodos', 'ema9'),
(9,  'ema20',           'ema',         '{5m,15m,4h}', 'float', 'EMA 20 períodos', 'ema20'),
(10, 'ema50',           'ema',         '{5m,15m,4h}', 'float', 'EMA 50 períodos', 'ema50'),
(11, 'ema200',          'ema',         '{5m,15m,4h}', 'float', 'EMA 200 períodos', 'ema200'),
(12, 'ema3_angle',      'ema',         '{5m,15m,4h}', 'float', 'Pendiente EMA3', 'ema3_angle'),
(13, 'ema9_angle',      'ema',         '{5m,15m,4h}', 'float', 'Pendiente EMA9', 'ema9_angle'),
(14, 'ema20_angle',     'ema',         '{5m,15m,4h}', 'float', 'Pendiente EMA20', 'ema20_angle'),
(15, 'ema50_angle',     'ema',         '{5m,15m,4h}', 'float', 'Pendiente EMA50', 'ema50_angle'),
(16, 'ema20_phase',     'ema',         '{15m,4h}',    'string', 'Fase EMA20 (nivel_1_long...nivel_3_short)', 'ema20_phase'),
(17, 'fib_zone',        'fibonacci',   '{5m,15m,4h}', 'integer', 'Zona Fibonacci (-6 a +6)', 'fibonacci_zone'),
(18, 'basis',           'fibonacci',   '{5m,15m,4h}', 'float', 'BASIS VWMA central', 'basis'),
(19, 'upper_1',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 1 (0.236)', 'upper_1'),
(20, 'upper_2',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 2 (0.382)', 'upper_2'),
(21, 'upper_3',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 3 (0.500)', 'upper_3'),
(22, 'upper_4',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 4 (0.618)', 'upper_4'),
(23, 'upper_5',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 5 (0.764)', 'upper_5'),
(24, 'upper_6',         'fibonacci',   '{5m,15m,4h}', 'float', 'Upper 6 (1.000)', 'upper_6'),
(25, 'lower_1',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 1', 'lower_1'),
(26, 'lower_2',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 2', 'lower_2'),
(27, 'lower_3',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 3', 'lower_3'),
(28, 'lower_4',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 4', 'lower_4'),
(29, 'lower_5',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 5', 'lower_5'),
(30, 'lower_6',         'fibonacci',   '{5m,15m,4h}', 'float', 'Lower 6', 'lower_6'),
(31, 'sar_trend_15m',   'sar',         '{15m}',       'integer', 'Tendencia SAR 15m (+1/-1)', 'sar_trend_15m'),
(32, 'sar_trend_4h',    'sar',         '{4h}',        'integer', 'Tendencia SAR 4h (+1/-1)', 'sar_trend_4h'),
(33, 'sar_ini_high_15m','sar',         '{15m}',       'boolean', 'SAR 15m recién cambió a alcista', 'sar_ini_high_15m'),
(34, 'sar_ini_low_15m', 'sar',         '{15m}',       'boolean', 'SAR 15m recién cambió a bajista', 'sar_ini_low_15m'),
(35, 'sar_ini_high_4h', 'sar',         '{4h}',        'integer', 'SAR 4h recién cambió a alcista', 'sar_ini_high_4h'),
(36, 'sar_ini_low_4h',  'sar',         '{4h}',        'integer', 'SAR 4h recién cambió a bajista', 'sar_ini_low_4h'),
(37, 'mtf_score',       'system',      '{15m}',       'float', 'MTF Score (-1 a +1)', 'mtf_score'),
(38, 'pine_signal',     'system',      '{5m,15m}',    'string', 'Señal PineScript', 'pinescript_signal'),
(39, 'spike_bullish',   'system',      '{5m,15m,4h}', 'boolean', 'Spike alcista', 'spike_bullish'),
(40, 'spike_bearish',   'system',      '{5m,15m,4h}', 'boolean', 'Spike bajista', 'spike_bearish'),
(41, 'spike_ratio',     'system',      '{5m,15m,4h}', 'float', 'Ratio volumen spike', 'spike_ratio'),
(42, 'regime',          'system',      '{15m}',       'string', 'Régimen de riesgo', 'regime'),
(43, 'structure_15m',   'structure',   '{15m}',       'string', 'Estructura 15m', 'structure_15m'),
(44, 'structure_4h',    'structure',   '{4h}',        'string', 'Estructura 4h', 'structure_4h'),
(45, 'allow_long_4h',   'structure',   '{4h}',        'boolean', 'Estructura 4h permite LONG', 'allow_long_4h'),
(46, 'allow_short_4h',  'structure',   '{4h}',        'boolean', 'Estructura 4h permite SHORT', 'allow_short_4h')
ON CONFLICT (id) DO NOTHING;

-- INSERTAR CONDICIONES
INSERT INTO strategy_conditions (id, name, variable_id, operator, value_type, value_literal, value_variable, value_list, value_min, value_max, timeframe, description)
VALUES
(1,  'ADX débil (<20)',       3,  '<',       'literal', 20,   NULL, NULL,  NULL,NULL,'15m','ADX < 20'),
(2,  'ADX moderado (20-35)',  3,  'BETWEEN', 'range',   NULL, NULL, NULL,  20,  35, '15m','20 <= ADX <= 35'),
(3,  'ADX agresivo (35-50)',  3,  'BETWEEN', 'range',   NULL, NULL, NULL,  35,  50, '15m','35 <= ADX <= 50'),
(4,  'ADX explosivo (>50)',   3,  '>',       'literal', 50,   NULL, NULL,  NULL,NULL,'15m','ADX > 50'),
(5,  'ADX cualquier fuerza',  3,  '>',       'literal', 0,    NULL, NULL,  NULL,NULL,'15m','ADX > 0'),
(6,  '+DI cruza > -DI',       4,  '>',       'variable',NULL, 'adx_minus_di',NULL,NULL,NULL,'15m','+DI > -DI'),
(7,  '-DI cruza > +DI',       5,  '>',       'variable',NULL, 'adx_plus_di', NULL,NULL,NULL,'15m','-DI > +DI'),
(8,  'EMA20 fase long (1-3)', 16, 'IN',      'list',    NULL, NULL, '{nivel_1_long,nivel_2_long,nivel_3_long}', NULL,NULL,'15m','EMA20 en fase alcista'),
(9,  'EMA20 fase short (1-3)',16, 'IN',      'list',    NULL, NULL, '{nivel_1_short,nivel_2_short,nivel_3_short}', NULL,NULL,'15m','EMA20 en fase bajista'),
(10, 'EMA20 nivel 1 long',    16, '==',      'list',    NULL, NULL, '{nivel_1_long}', NULL,NULL,'15m','EMA20 nivel 1 long'),
(11, 'EMA20 ángulo positivo', 14, '>=',      'literal', 0,    NULL, NULL,  NULL,NULL,'15m','EMA20 apuntando arriba'),
(12, 'EMA20 ángulo negativo', 14, '<',       'literal', 0,    NULL, NULL,  NULL,NULL,'15m','EMA20 apuntando abajo'),
(13, 'EMA9 ángulo positivo',  13, '>=',      'literal', 0,    NULL, NULL,  NULL,NULL,'15m','EMA9 apuntando arriba'),
(14, 'EMA9 ángulo negativo',  13, '<',       'literal', 0,    NULL, NULL,  NULL,NULL,'15m','EMA9 apuntando abajo'),
(15, 'EMA50 ángulo positivo', 15, '>=',      'literal', 0,    NULL, NULL,  NULL,NULL,'15m','EMA50 apuntando arriba'),
(16, 'Zona positiva (>0)',    17, '>',       'literal', 0,    NULL, NULL,  NULL,NULL,'15m','Precio sobre basis'),
(17, 'Zona negativa (<0)',    17, '<',       'literal', 0,    NULL, NULL,  NULL,NULL,'15m','Precio bajo basis'),
(18, 'Zona extendida+ (>=3)', 17, '>=',      'literal', 3,    NULL, NULL,  NULL,NULL,'15m','Zona +3 o más'),
(19, 'Zona extendida- (<=-3)',17, '<=',      'literal', -3,   NULL, NULL,  NULL,NULL,'15m','Zona -3 o menos'),
(20, 'Precio toca lower_5',   1,  '<=',      'variable',NULL, 'lower_5',NULL,NULL,NULL,'15m','Precio <= lower_5'),
(21, 'Precio toca lower_6',   1,  '<=',      'variable',NULL, 'lower_6',NULL,NULL,NULL,'15m','Precio <= lower_6'),
(22, 'Precio toca upper_5',   1,  '>=',      'variable',NULL, 'upper_5',NULL,NULL,NULL,'15m','Precio >= upper_5'),
(23, 'Precio toca upper_6',   1,  '>=',      'variable',NULL, 'upper_6',NULL,NULL,NULL,'15m','Precio >= upper_6'),
(24, 'SAR 15m alcista',       31, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'15m','SAR 15m +1'),
(25, 'SAR 15m bajista',       31, '==',      'literal', -1,   NULL, NULL,  NULL,NULL,'15m','SAR 15m -1'),
(26, 'SAR 4h alcista',        32, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'4h', 'SAR 4h +1'),
(27, 'SAR 4h bajista',        32, '==',      'literal', -1,   NULL, NULL,  NULL,NULL,'4h', 'SAR 4h -1'),
(28, 'SAR 15m cambió LONG',   33, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'15m','SAR 15m ini_high'),
(29, 'SAR 15m cambió SHORT',  34, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'15m','SAR 15m ini_low'),
(30, 'SAR 4h cambió LONG',    35, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'4h', 'SAR 4h ini_high'),
(31, 'SAR 4h cambió SHORT',   36, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'4h', 'SAR 4h ini_low'),
(32, 'MTF fuerte+ (>=0.50)',  37, '>=',      'literal', 0.50, NULL, NULL,  NULL,NULL,'15m','MTF >= 0.50'),
(33, 'MTF débil+ (>=0.20)',   37, '>=',      'literal', 0.20, NULL, NULL,  NULL,NULL,'15m','MTF >= 0.20'),
(34, 'MTF fuerte- (<=-0.50)', 37, '<=',      'literal', -0.50,NULL, NULL,  NULL,NULL,'15m','MTF <= -0.50'),
(35, 'MTF débil- (<=-0.20)',  37, '<=',      'literal', -0.20,NULL, NULL,  NULL,NULL,'15m','MTF <= -0.20'),
(36, 'PineScript Buy',        38, 'IN',      'list',    NULL, NULL, '{Buy}',  NULL,NULL,'15m','Señal Buy'),
(37, 'PineScript Sell',       38, 'IN',      'list',    NULL, NULL, '{Sell}', NULL,NULL,'15m','Señal Sell'),
(38, 'Spike alcista',         39, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'15m','spike_bullish=true'),
(39, 'Spike bajista',         40, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'15m','spike_bearish=true'),
(40, 'Estructura 4h LONG ok', 45, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'4h', 'allow_long_4h'),
(41, 'Estructura 4h SHORT ok',46, '==',      'literal', 1,    NULL, NULL,  NULL,NULL,'4h', 'allow_short_4h'),
(42, 'Dist basis >1.5%',      2,  '>=',      'literal', 1.5,  NULL, NULL,  NULL,NULL,'15m','dist_basis_pct >= 1.5'),
(43, 'Dist basis >3.0%',      2,  '>=',      'literal', 3.0,  NULL, NULL,  NULL,NULL,'4h', 'dist_basis_pct >= 3.0'),
(44, 'Mercado débil',         6,  'IN',      'list',    NULL, NULL, '{debil}',    NULL,NULL,'15m','ADX velocity = debil'),
(45, 'Mercado moderado+',     6,  'IN',      'list',    NULL, NULL, '{moderado,agresivo,explosivo}',NULL,NULL,'15m','ADX velocity moderado o más')
ON CONFLICT (id) DO NOTHING;

-- INSERTAR REGLAS V2
INSERT INTO strategy_rules_v2 (id, rule_code, name, strategy_type, direction, cycle, condition_ids, condition_logic, min_score, condition_weights, market_types, enabled, priority, confidence, version, notes)
VALUES
(1001, 'Aa11', 'LONG débil: EMA20+ ADX<20 +DI cruza', 'scalping', 'long', '15m', '{11,1,6,24,26,40}', 'AND', 0.50, '{"11":0.15,"1":0.20,"6":0.25,"24":0.15,"26":0.15,"40":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.65, 1, 'Mercado débil alcista con +DI cruzando'),
(1002, 'Aa12', 'LONG soporte: precio toca lower_5/6', 'scalping', 'long', '15m', '{11,20,24,26,36,40}', 'AND', 0.60, '{"11":0.10,"20":0.30,"24":0.15,"26":0.15,"36":0.20,"40":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'Precio toca soporte lower_5 con confirmación'),
(1003, 'Aa21', 'LONG momentum: EMA9+EMA50 ángulos+', 'scalping', 'long', '15m', '{11,13,16,26,32,40}', 'AND', 0.65, '{"11":0.15,"13":0.15,"16":0.15,"26":0.20,"32":0.25,"40":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'Momentum alcista multi-EMA'),
(1004, 'Aa22', 'LONG principal: EMA20 fase long + ADX fuerte', 'scalping', 'long', '15m', '{8,2,26,32,36,40}', 'AND', 0.60, '{"8":0.25,"2":0.15,"26":0.20,"32":0.20,"36":0.10,"40":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.75, 1, 'Regla principal LONG — EMA20 fase long'),
(1005, 'Aa23', 'LONG scalp SAR 15m cambió + Pine Buy', 'scalping', 'long', '5m', '{28,26,36,40}', 'AND', 0.60, '{"28":0.35,"26":0.25,"36":0.30,"40":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'SAR 15m cambió a alcista + PineScript Buy'),
(1006, 'Aa24', 'LONG agresivo: zona extendida + explosivo', 'scalping', 'long', '15m', '{18,32,26,36,45}', 'AND', 0.75, '{"18":0.20,"32":0.30,"26":0.20,"36":0.20,"45":0.10}', '{crypto_futures}', true, 2, 0.75, 1, 'Zona +3 con momentum explosivo'),
(1011, 'Bb11', 'SHORT débil: EMA20- ADX<20 -DI cruza', 'scalping', 'short', '15m', '{12,1,7,25,27,41}', 'AND', 0.50, '{"12":0.15,"1":0.20,"7":0.25,"25":0.15,"27":0.15,"41":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.65, 1, 'Mercado débil bajista con -DI cruzando'),
(1012, 'Bb12', 'SHORT resistencia: precio toca upper_5/6', 'scalping', 'short', '15m', '{12,22,25,27,37,41}', 'AND', 0.60, '{"12":0.10,"22":0.30,"25":0.15,"27":0.15,"37":0.20,"41":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'Precio toca resistencia upper_5'),
(1013, 'Bb21', 'SHORT momentum: EMA20 fase short + MTF-', 'scalping', 'short', '15m', '{9,14,17,27,34,41}', 'AND', 0.65, '{"9":0.25,"14":0.10,"17":0.10,"27":0.20,"34":0.25,"41":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'EMA20 en fase short + MTF negativo'),
(1014, 'Bb22', 'SHORT principal: EMA20 fase short + ADX fuerte', 'scalping', 'short', '15m', '{9,2,27,34,37,41}', 'AND', 0.60, '{"9":0.25,"2":0.15,"27":0.20,"34":0.20,"37":0.10,"41":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.75, 1, 'Regla principal SHORT'),
(1015, 'Bb23', 'SHORT scalp SAR 15m cambió + Pine Sell', 'scalping', 'short', '5m', '{29,27,37,41}', 'AND', 0.60, '{"29":0.35,"27":0.25,"37":0.30,"41":0.10}', '{crypto_futures,forex_futures}', true, 1, 0.70, 1, 'SAR 15m cambió a bajista + PineScript Sell'),
(2001, 'Dd21_15m', 'SWING LONG 15m: caída madura banda lower', 'swing', 'long', '15m', '{42,26,40}', 'AND', 0.65, '{"42":0.40,"26":0.35,"40":0.25}', '{crypto_futures,forex_futures,crypto_spot,stocks_spot}', true, 2, 0.70, 1, 'LIMIT LONG extremo inferior maduro — 15m'),
(2002, 'Dd21_4h', 'SWING LONG 4h: caída madura macro', 'swing', 'long', '4h', '{43,26,40}', 'AND', 0.70, '{"43":0.45,"26":0.30,"40":0.25}', '{crypto_futures,forex_futures,crypto_spot,stocks_spot}', true, 2, 0.75, 1, 'LIMIT LONG extremo inferior macro — 4h'),
(2011, 'Dd11_15m', 'SWING SHORT 15m: subida madura banda upper', 'swing', 'short', '15m', '{42,27,41}', 'AND', 0.65, '{"42":0.40,"27":0.35,"41":0.25}', '{crypto_futures,forex_futures}', true, 2, 0.70, 1, 'LIMIT SHORT extremo superior maduro — 15m'),
(2012, 'Dd11_4h', 'SWING SHORT 4h: subida madura macro', 'swing', 'short', '4h', '{43,27,41}', 'AND', 0.70, '{"43":0.45,"27":0.30,"41":0.25}', '{crypto_futures,forex_futures}', true, 2, 0.75, 1, 'LIMIT SHORT extremo superior macro — 4h')
ON CONFLICT (id) DO NOTHING;

-- VERIFICACIÓN
SELECT 'strategy_variables' AS tabla, COUNT(*) AS registros FROM strategy_variables
UNION ALL
SELECT 'strategy_conditions', COUNT(*) FROM strategy_conditions
UNION ALL
SELECT 'strategy_rules_v2', COUNT(*) FROM strategy_rules_v2;

-- <<< migration_023_strategy_engine_v1.sql <<<


-- >>> migration_024_auth_system.sql >>>
-- ==========================================================
-- MIGRATION 024 — eTrade Auth & Admin System
-- ==========================================================

-- 1. Tabla: roles
CREATE TABLE IF NOT EXISTS roles (
    id                  BIGSERIAL PRIMARY KEY,
    nombre              VARCHAR(50) UNIQUE NOT NULL,
    codigo_registro     VARCHAR(100) UNIQUE NOT NULL,
    descripcion         TEXT,
    activo              BOOLEAN DEFAULT true,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Tabla: usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre              VARCHAR(100) NOT NULL,
    correo              VARCHAR(100) UNIQUE NOT NULL,
    password            VARCHAR(255) NOT NULL,
    rol_id              BIGINT REFERENCES roles(id) ON DELETE SET NULL,
    verificado          BOOLEAN DEFAULT false,
    token_verificacion  VARCHAR(255),
    token_expiracion    TIMESTAMPTZ,
    token_reset_pass    VARCHAR(255),
    token_reset_exp     TIMESTAMPTZ,
    fecha_registro      TIMESTAMPTZ DEFAULT NOW(),
    activo              BOOLEAN DEFAULT true,
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Seed inicial de roles
INSERT INTO roles (nombre, codigo_registro, descripcion)
VALUES 
('CEO', 'etrade369', 'Acceso total al sistema y gestión de usuarios.'),
('Visita', 'etrade123', 'Acceso limitado de solo lectura a la plataforma.')
ON CONFLICT (nombre) DO NOTHING;

-- 4. Índices para búsqueda rápida
CREATE INDEX IF NOT EXISTS idx_usuarios_correo ON usuarios(correo);
CREATE INDEX IF NOT EXISTS idx_usuarios_rol ON usuarios(rol_id);
CREATE INDEX IF NOT EXISTS idx_roles_codigo ON roles(codigo_registro);

-- <<< migration_024_auth_system.sql <<<


-- >>> migration_025_stocks_module.sql >>>
-- ============================================================
-- eTrader v4.5 — STOCKS MODULE — Sprint 5 Migration
-- Creates all 10 tables required for the Stocks module
-- ============================================================

-- 1. WATCHLIST DIARIO (Capa 0: Universe Builder output)
CREATE TABLE IF NOT EXISTS watchlist_daily (
  id               SERIAL PRIMARY KEY,
  ticker           VARCHAR(10) NOT NULL,
  pool_type        VARCHAR(20),           -- core | tactical
  catalyst_score   INTEGER,
  catalyst_type    VARCHAR(50),
  market_regime    VARCHAR(20),
  hard_filter_pass BOOLEAN DEFAULT true,
  date             DATE DEFAULT CURRENT_DATE,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_watchlist_date ON watchlist_daily(date DESC, catalyst_score DESC);

-- 2. MARKET DATA 5M (OHLCV from yfinance / IB)
CREATE TABLE IF NOT EXISTS market_data_5m (
  id               SERIAL PRIMARY KEY,
  ticker           VARCHAR(10),
  timestamp        TIMESTAMPTZ,
  open             NUMERIC,
  high             NUMERIC,
  low              NUMERIC,
  close            NUMERIC,
  volume           BIGINT,
  rvol             NUMERIC,
  spread_pct       NUMERIC,
  slippage_est     NUMERIC,
  liquidity_score  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_mkt5m_ticker_ts ON market_data_5m(ticker, timestamp DESC);
-- Unique constraint for upsert
CREATE UNIQUE INDEX IF NOT EXISTS idx_mkt5m_upsert ON market_data_5m(ticker, timestamp);

-- 3. TECHNICAL SCORES (Capa 2 output)
CREATE TABLE IF NOT EXISTS technical_scores (
  id                SERIAL PRIMARY KEY,
  ticker            VARCHAR(10),
  timestamp         TIMESTAMPTZ,
  rsi_14            NUMERIC,
  atr_14            NUMERIC,
  bollinger_squeeze BOOLEAN,
  macd_signal       VARCHAR(20),
  ema_alignment     VARCHAR(20),
  rvol              NUMERIC,
  fib_level         VARCHAR(20),
  mtf_confirmed     BOOLEAN,
  technical_score   NUMERIC,
  signals_json      JSONB
);
CREATE INDEX IF NOT EXISTS idx_techscores_ticker_ts ON technical_scores(ticker, timestamp DESC);

-- 4. FUNDAMENTAL CACHE (Capa 3 output — refreshed periodically)
CREATE TABLE IF NOT EXISTS fundamental_cache (
  id                   SERIAL PRIMARY KEY,
  ticker               VARCHAR(10) UNIQUE,
  valuation_mode       VARCHAR(5),          -- A (value) | B (growth)
  intrinsic_value      NUMERIC,
  current_price        NUMERIC,
  margin_of_safety     NUMERIC,
  valuation_status     VARCHAR(30),
  fundamental_score    NUMERIC,
  mode_b_metrics_json  JSONB,
  confidence           VARCHAR(20),
  refreshed_at         TIMESTAMPTZ DEFAULT NOW()
);

-- 5. CONTEXT SCORES (Capa 4 output — Gemini + Grok)
CREATE TABLE IF NOT EXISTS context_scores (
  id                SERIAL PRIMARY KEY,
  ticker            VARCHAR(10),
  date              DATE DEFAULT CURRENT_DATE,
  catalyst_score    INTEGER,
  catalyst_type     VARCHAR(50),
  sentiment_score   NUMERIC,
  narrative         TEXT,
  context_score     NUMERIC,
  regime_adjustment NUMERIC
);
CREATE INDEX IF NOT EXISTS idx_ctx_ticker_date ON context_scores(ticker, date DESC);

-- 6. TRADE OPPORTUNITIES (Capa 5 output — Claude decisions)
CREATE TABLE IF NOT EXISTS trade_opportunities (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker           VARCHAR(10) NOT NULL,
  meta_score       NUMERIC,
  risk_score       NUMERIC,
  trade_type       VARCHAR(20),          -- swing_trade | scalping | wait | no_trade
  quadrant         VARCHAR(5),           -- A | B | C | D
  entry_zone_low   NUMERIC,
  entry_zone_high  NUMERIC,
  stop_loss        NUMERIC,
  target_1         NUMERIC,
  target_2         NUMERIC,
  capital_usd      NUMERIC,
  shares           INTEGER,
  rr_ratio         NUMERIC,
  status           VARCHAR(20) DEFAULT 'pending',  -- pending | confirmed | rejected
  created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opp_status ON trade_opportunities(status, created_at DESC);

-- 7. TRADES ACTIVE (positions currently open)
CREATE TABLE IF NOT EXISTS trades_active (
  id                    UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  opportunity_id        UUID REFERENCES trade_opportunities(id),
  ticker                VARCHAR(10),
  entry_price           NUMERIC,
  entry_time            TIMESTAMPTZ,
  shares                INTEGER,
  stop_loss             NUMERIC,
  target_1              NUMERIC,
  target_2              NUMERIC,
  trailing_stop_active  BOOLEAN DEFAULT false,
  current_price         NUMERIC,
  unrealized_pnl        NUMERIC,
  status                VARCHAR(20) DEFAULT 'active'
);

-- 8. TRADES JOURNAL (Capa 7 — closed trades history)
CREATE TABLE IF NOT EXISTS trades_journal (
  id               UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  ticker           VARCHAR(10),
  entry_date       TIMESTAMPTZ,
  exit_date        TIMESTAMPTZ,
  trade_type       VARCHAR(20),
  valuation_mode   VARCHAR(5),
  entry_price      NUMERIC,
  exit_price       NUMERIC,
  shares           INTEGER,
  slippage_actual  NUMERIC,
  meta_score       NUMERIC,
  risk_score       NUMERIC,
  pnl_usd          NUMERIC,
  pnl_pct          NUMERIC,
  result           VARCHAR(20),         -- win | loss | breakeven
  exit_reason      VARCHAR(50),
  market_regime    VARCHAR(20),
  catalyst_type    VARCHAR(50)
);
CREATE INDEX IF NOT EXISTS idx_journal_exit ON trades_journal(exit_date DESC);

-- 9. PERFORMANCE METRICS (rolling daily aggregation)
CREATE TABLE IF NOT EXISTS performance_metrics (
  id                    SERIAL PRIMARY KEY,
  date                  DATE DEFAULT CURRENT_DATE,
  win_rate_overall      NUMERIC,
  win_rate_swing_a      NUMERIC,
  win_rate_scalping_c   NUMERIC,
  avg_rr_achieved       NUMERIC,
  avg_slippage_actual   NUMERIC,
  sharpe_rolling_20     NUMERIC,
  regime                VARCHAR(20),
  trades_count          INTEGER
);

-- 10. STOCKS CONFIG (system parameters — editable via UI)
CREATE TABLE IF NOT EXISTS stocks_config (
  id          SERIAL PRIMARY KEY,
  key         VARCHAR(100) UNIQUE,
  value       TEXT,
  description TEXT,
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ── Default Configuration ──
INSERT INTO stocks_config (key, value, description) VALUES
  ('total_capital_usd',           '5000',    'Capital total asignado al módulo Stocks'),
  ('max_pct_per_trade',           '20',      'Max % del capital por trade'),
  ('min_pct_per_trade',           '10',      'Min % del capital por trade'),
  ('max_simultaneous_positions',  '3',       'Max posiciones abiertas simultáneamente'),
  ('max_stock_price',             '50',      'Precio máximo de acción (hard filter)'),
  ('min_daily_volume',            '500000',  'Volumen mínimo diario en acciones'),
  ('min_market_cap_usd',          '300000000','Market cap mínimo ($300M)'),
  ('meta_score_threshold',        '70',      'Meta-Score mínimo para llamar Claude'),
  ('technical_score_threshold',   '60',      'Technical Score mínimo para Capas 3+4'),
  ('mtf_confirmation_required',   '4',       'Timeframes confirmando (de 5)'),
  ('risk_score_max_trade',        '8',       'Risk Score max — 9-10 = no trade'),
  ('scalping_max_capital_pct',    '10',      'Max % capital para Quad C (scalping)'),
  ('swing_atr_multiplier',        '2.0',     'Multiplicador ATR para SL swing'),
  ('scalping_atr_multiplier',     '1.0',     'Multiplicador ATR para SL scalping'),
  ('rvol_spike_threshold',        '2.5',     'RVOL multiplicador para Volume Spike'),
  ('slippage_max_reject',         '0.5',     'Max slippage % — rechazar si mayor'),
  ('paper_mode_active',           'true',    'Modo paper trading activo'),
  ('kill_switch_active',          'false',   'Emergency stop — detiene todo'),
  ('bear_capital_reduction_pct',  '30',      '% reducción capital en Bear'),
  ('vix_bear_threshold',          '25',      'VIX > 25 → Bear Market'),
  ('vix_bull_threshold',          '18',      'VIX < 18 → Bull Market'),
  ('watchlist_core_count',        '30',      'Tickers core estables'),
  ('scan_interval_minutes',       '5',       'Frecuencia worker en mercado'),
  ('premarket_scan_start',        '09:00',   'Inicio scan pre-market (ET)'),
  ('market_open',                 '09:30',   'Apertura mercado (ET)'),
  ('market_close',                '16:00',   'Cierre mercado (ET)')
ON CONFLICT (key) DO NOTHING;

-- ── Verification ──
SELECT table_name FROM information_schema.tables
  WHERE table_schema = 'public'
  AND table_name IN (
    'watchlist_daily', 'market_data_5m', 'technical_scores',
    'fundamental_cache', 'context_scores', 'trade_opportunities',
    'trades_active', 'trades_journal', 'performance_metrics',
    'stocks_config'
  )
ORDER BY table_name;
-- Expected: 10 rows

-- <<< migration_025_stocks_module.sql <<<


-- >>> migration_026_smart_limit.sql >>>
-- migration_026_smart_limit.sql
ALTER TABLE market_snapshot
ADD COLUMN IF NOT EXISTS
  movement_type       VARCHAR(30),
ADD COLUMN IF NOT EXISTS
  basis_slope_pct     NUMERIC,
ADD COLUMN IF NOT EXISTS
  ema200_slope_pct    NUMERIC,
ADD COLUMN IF NOT EXISTS
  movement_confidence NUMERIC,
ADD COLUMN IF NOT EXISTS
  signal_bias         VARCHAR(20),
ADD COLUMN IF NOT EXISTS
  smart_limit_long    NUMERIC,
ADD COLUMN IF NOT EXISTS
  smart_limit_short   NUMERIC,
ADD COLUMN IF NOT EXISTS
  smart_limit_band_long  VARCHAR(20),
ADD COLUMN IF NOT EXISTS
  smart_limit_band_short VARCHAR(20),
ADD COLUMN IF NOT EXISTS
  movement_description TEXT;

ALTER TABLE pending_orders
ADD COLUMN IF NOT EXISTS movement_type VARCHAR(30),
ADD COLUMN IF NOT EXISTS signal_quality VARCHAR(10),
ADD COLUMN IF NOT EXISTS fib_zone_entry INTEGER;

-- <<< migration_026_smart_limit.sql <<<


-- >>> migration_026_valuation_engine.sql >>>

-- eTrader v4.5 — VALUATION ENGINE Migration
-- Adds columns to fundamental_cache for mathematical valuation storage

ALTER TABLE fundamental_cache
ADD COLUMN IF NOT EXISTS piotroski_score INTEGER,
ADD COLUMN IF NOT EXISTS piotroski_detail JSONB,
ADD COLUMN IF NOT EXISTS graham_number NUMERIC,
ADD COLUMN IF NOT EXISTS graham_margin NUMERIC,
ADD COLUMN IF NOT EXISTS dcf_intrinsic NUMERIC,
ADD COLUMN IF NOT EXISTS dcf_upside_pct NUMERIC,
ADD COLUMN IF NOT EXISTS altman_z_score NUMERIC,
ADD COLUMN IF NOT EXISTS altman_zone VARCHAR(20),
ADD COLUMN IF NOT EXISTS math_score NUMERIC,
ADD COLUMN IF NOT EXISTS ia_score NUMERIC,
ADD COLUMN IF NOT EXISTS data_source VARCHAR(50),
ADD COLUMN IF NOT EXISTS valuation_status VARCHAR(30),
ADD COLUMN IF NOT EXISTS composite_intrinsic NUMERIC;

COMMENT ON COLUMN fundamental_cache.piotroski_score IS 'Piotroski F-Score (0-9)';
COMMENT ON COLUMN fundamental_cache.graham_number IS 'Intrinsic value using Graham Number formula';
COMMENT ON COLUMN fundamental_cache.dcf_intrinsic IS 'Intrinsic value using Discounted Cash Flow';
COMMENT ON COLUMN fundamental_cache.math_score IS 'Composite Pro Score based only on mathematical models (1-10)';
COMMENT ON COLUMN fundamental_cache.ia_score IS 'Pro Score provided by AI (1-10)';

-- <<< migration_026_valuation_engine.sql <<<


-- >>> migration_027_candle_signals.sql >>>
-- ═══════════════════════════════════════════════════════════════════════════
-- MIGRATION 027: Candle Signal Validator — Audit Table
-- ANTIGRAVITY · Candle Signal Validator v1.0
-- Tables: candle_signals
-- ═══════════════════════════════════════════════════════════════════════════

-- ─── CANDLE SIGNALS AUDIT TABLE ─────────────────────────────────────────────
-- Stores every BUY/SELL signal detected by the candle pattern engine
CREATE TABLE IF NOT EXISTS candle_signals (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    pair          TEXT NOT NULL,                        -- "BTC/USDT", "EURUSD", "AAPL"
    market        TEXT NOT NULL CHECK (market IN ('crypto', 'forex', 'stocks')),
    timeframe     TEXT NOT NULL CHECK (timeframe IN ('4H', '1D')),
    
    -- Pattern details
    pattern_id    INT NOT NULL,                        -- 1–26
    pattern_name  TEXT NOT NULL,                        -- "Engulfing Alcista", etc.
    signal_type   TEXT NOT NULL,                        -- "Alcista", "Bajista", "Reversión Alcista", etc.
    action        TEXT NOT NULL CHECK (action IN ('BUY', 'SELL', 'HOLD')),
    confidence    NUMERIC(5,1) DEFAULT 0,              -- 0–100
    candles_used  INT DEFAULT 1,                       -- 1, 2 or 3
    
    -- Strategy
    strategy_code TEXT,                                -- "Aa41", "Bb41", "PRO_CANDLE_BUY", etc.
    pool_type     TEXT,                                -- "PRO" or "HOT" (stocks only)
    
    -- OHLCV snapshot at signal time
    ohlc_open     NUMERIC(20,8),
    ohlc_high     NUMERIC(20,8),
    ohlc_low      NUMERIC(20,8),
    ohlc_close    NUMERIC(20,8),
    ohlc_volume   NUMERIC(20,2),
    
    -- Execution result
    executed      BOOLEAN DEFAULT FALSE,
    execution_id  UUID,                                -- links to orders/positions
    
    -- Timestamps
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    
    -- Performance tracking (filled after close)
    result_pnl    NUMERIC(20,4),
    result_status TEXT                                  -- "win", "loss", "pending"
);

-- ─── INDEXES ────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_candle_signals_pair_tf 
    ON candle_signals(pair, timeframe);

CREATE INDEX IF NOT EXISTS idx_candle_signals_market_action 
    ON candle_signals(market, action);

CREATE INDEX IF NOT EXISTS idx_candle_signals_created_at 
    ON candle_signals(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_candle_signals_strategy 
    ON candle_signals(strategy_code);

-- ─── RLS POLICIES ───────────────────────────────────────────────────────────
ALTER TABLE candle_signals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow service role full access on candle_signals"
    ON candle_signals
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- ─── COMMENTS ───────────────────────────────────────────────────────────────
COMMENT ON TABLE candle_signals IS 'ANTIGRAVITY Candle Signal Validator — Audit log for all detected BUY/SELL/HOLD candle patterns across Crypto, Forex, and Stocks.';
COMMENT ON COLUMN candle_signals.pattern_id IS 'Pattern ID 1-26 from the ANTIGRAVITY catalog';
COMMENT ON COLUMN candle_signals.strategy_code IS 'Strategy: Aa41/Bb41 (crypto/forex), PRO_CANDLE_BUY/SELL (stocks pro), HOT_CANDLE_BUY/SELL (stocks hot)';
COMMENT ON COLUMN candle_signals.confidence IS 'Pattern purity score 0-100 with volume confirmation bonus';

-- <<< migration_027_candle_signals.sql <<<


-- >>> migration_027b_add_fib_zone.sql >>>
-- Add fibonacci_zone column to candle_signals table
ALTER TABLE candle_signals ADD COLUMN IF NOT EXISTS fib_zone INT DEFAULT 0;
COMMENT ON COLUMN candle_signals.fib_zone IS 'Fibonacci band zone at signal time (-6 to +6)';

-- <<< migration_027b_add_fib_zone.sql <<<


-- >>> migration_032_dca_executed.sql >>>
-- Migration: Add dca_executed to positions

ALTER TABLE public.positions 
ADD COLUMN IF NOT EXISTS dca_executed BOOLEAN DEFAULT FALSE;

-- <<< migration_032_dca_executed.sql <<<


-- >>> migration_033_halcon_centinela.sql >>>
-- ============================================================
-- HALCÓN CENTINELA — Database Migration
-- eTrade v5.0 — Gestor de Cierre Proactivo Multi-Timeframe
-- ============================================================

-- ── 1. Tabla de log de scores HALCÓN ──
-- Registra cada evaluación del motor de scoring por posición
CREATE TABLE IF NOT EXISTS halcon_scores_log (
    id BIGSERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_profile TEXT DEFAULT 'TENDENCIA_SOSTENIDA',
    market_type TEXT DEFAULT 'forex',
    -- Scores por capa (antes de ajustes de régimen)
    score_1d INT DEFAULT 0,
    score_4h INT DEFAULT 0,
    score_15m INT DEFAULT 0,
    score_5m INT DEFAULT 0,
    score_1m INT DEFAULT 0,
    -- Ajustes RSI por capa
    rsi_adj_1d INT DEFAULT 0,
    rsi_adj_4h INT DEFAULT 0,
    rsi_adj_15m INT DEFAULT 0,
    rsi_adj_5m INT DEFAULT 0,
    -- Régimen y compresión
    regime TEXT,
    regime_adx FLOAT,
    compression_index FLOAT,
    compression_timeframe TEXT,
    fib_zone INT,
    fib_multiplier FLOAT DEFAULT 1.0,
    -- Resultado final
    score_final FLOAT NOT NULL,
    semaforo TEXT NOT NULL,
    decision TEXT NOT NULL,
    squeeze_active BOOLEAN DEFAULT FALSE,
    volume_confirmed BOOLEAN,
    -- Ejecución
    executed BOOLEAN DEFAULT FALSE,
    pnl_at_evaluation FLOAT,
    -- Detalle completo (JSON)
    detail JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_halcon_scores_position ON halcon_scores_log(position_id);
CREATE INDEX IF NOT EXISTS idx_halcon_scores_symbol ON halcon_scores_log(symbol);
CREATE INDEX IF NOT EXISTS idx_halcon_scores_created ON halcon_scores_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_halcon_scores_decision ON halcon_scores_log(decision);

-- ── 2. Tabla de decisiones CENTINELA ──
-- Registra cada decisión de cierre/mantener con contexto completo
CREATE TABLE IF NOT EXISTS centinela_decisions_log (
    id BIGSERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market_type TEXT DEFAULT 'forex',
    decision TEXT NOT NULL,
    reason TEXT,
    score_final FLOAT,
    pnl_at_decision FLOAT,
    entry_profile TEXT,
    -- ORÁCULO
    oraculo_override BOOLEAN DEFAULT FALSE,
    oraculo_event TEXT,
    -- Ejecución
    executed BOOLEAN DEFAULT FALSE,
    execution_result JSONB,
    -- Arbitraje
    blocked_by TEXT,
    closing_in_progress_set BOOLEAN DEFAULT FALSE,
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_centinela_decisions_position ON centinela_decisions_log(position_id);
CREATE INDEX IF NOT EXISTS idx_centinela_decisions_symbol ON centinela_decisions_log(symbol);
CREATE INDEX IF NOT EXISTS idx_centinela_decisions_created ON centinela_decisions_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_centinela_decisions_executed ON centinela_decisions_log(executed);

-- ── 3. Cache de eventos económicos para ORÁCULO ──
CREATE TABLE IF NOT EXISTS oraculo_events (
    id BIGSERIAL PRIMARY KEY,
    event_name TEXT NOT NULL,
    country TEXT,
    currency TEXT,
    impact TEXT NOT NULL,
    event_datetime TIMESTAMPTZ NOT NULL,
    is_global BOOLEAN DEFAULT FALSE,
    -- Pausa
    trading_paused_symbols TEXT[],
    pause_start TIMESTAMPTZ,
    pause_end TIMESTAMPTZ,
    -- Estado
    processed BOOLEAN DEFAULT FALSE,
    actions_taken JSONB,
    -- Sync
    source TEXT DEFAULT 'finnhub',
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    -- Evitar duplicados
    UNIQUE(event_name, event_datetime)
);

CREATE INDEX IF NOT EXISTS idx_oraculo_events_datetime ON oraculo_events(event_datetime);
CREATE INDEX IF NOT EXISTS idx_oraculo_events_currency ON oraculo_events(currency);
CREATE INDEX IF NOT EXISTS idx_oraculo_events_processed ON oraculo_events(processed);

-- ── 4. Estado CENTINELA por posición ──
-- Almacena el estado de la máquina de estados de cada posición
CREATE TABLE IF NOT EXISTS centinela_position_state (
    position_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    market_type TEXT DEFAULT 'forex',
    -- Estado CENTINELA
    halcon_state TEXT DEFAULT 'NEUTRAL',
    closing_in_progress BOOLEAN DEFAULT FALSE,
    -- Historial
    last_close_action_at TIMESTAMPTZ,
    last_score_final FLOAT,
    last_semaforo TEXT,
    last_decision TEXT,
    -- Cooldown
    cooldown_until TIMESTAMPTZ,
    -- Perfil
    entry_profile TEXT DEFAULT 'TENDENCIA_SOSTENIDA',
    partial_closed_pct FLOAT DEFAULT 0,
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_centinela_state_symbol ON centinela_position_state(symbol);
CREATE INDEX IF NOT EXISTS idx_centinela_state_closing ON centinela_position_state(closing_in_progress);

-- ── 5. Configuración HALCÓN en system_config ──
-- Inserta parámetros configurables como pares clave-valor
INSERT INTO system_config (key, value)
VALUES 
    ('halcon_enabled', 'true'),
    ('halcon_min_profit_usd', '1.0'),
    ('halcon_partial_close_pct', '0.50'),
    ('halcon_adx_range_threshold', '15'),
    ('halcon_adx_trend_threshold', '30'),
    ('halcon_compression_threshold', '0.15'),
    ('halcon_volume_multiplier', '1.3'),
    ('halcon_volume_lookback', '10'),
    ('halcon_atr_pct_threshold', '0.008'),
    ('halcon_rsi_extreme_low', '20'),
    ('halcon_rsi_extreme_high', '80'),
    ('halcon_rsi_extreme_points', '25'),
    ('halcon_rsi_divergence_points', '35'),
    ('halcon_ema_proximity_pct', '0.15'),
    ('halcon_oraculo_enabled', 'true'),
    ('halcon_oraculo_pre_event_min', '60'),
    ('halcon_oraculo_post_event_min', '60'),
    ('halcon_oraculo_close_pnl_threshold', '-5.0'),
    ('halcon_oraculo_bracket_sl_floor', '-8.0'),
    ('halcon_oraculo_calendar_sync_min', '60')
ON CONFLICT (key) DO NOTHING;

-- ── 6. Retención automática — limpiar logs antiguos (>30 días) ──
-- Puede ejecutarse como cron job o scheduled task
-- DELETE FROM halcon_scores_log WHERE created_at < NOW() - INTERVAL '30 days';
-- DELETE FROM centinela_decisions_log WHERE created_at < NOW() - INTERVAL '30 days';
-- DELETE FROM oraculo_events WHERE event_datetime < NOW() - INTERVAL '7 days';

-- <<< migration_033_halcon_centinela.sql <<<


-- >>> migration_034_rebote_aduana.sql >>>
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

-- <<< migration_034_rebote_aduana.sql <<<


-- >>> migration_035_radar_cascada.sql >>>
-- ============================================================================
-- migration_035_radar_cascada.sql
-- RADAR and CASCADA modules integration schema updates
-- ============================================================================

-- 1. Add 'origen' column to forex_positions and positions (if not already present)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'origen'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN origen VARCHAR(50) DEFAULT 'STANDARD';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'origen'
    ) THEN
        ALTER TABLE positions ADD COLUMN origen VARCHAR(50) DEFAULT 'STANDARD';
    END IF;
END $$;

-- 2. Add CASCADA state columns to forex_positions and positions
DO $$
BEGIN
    -- forex_positions
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'cascade_level'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN cascade_level INT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'cascade_hold'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN cascade_hold BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'pnl_pico'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN pnl_pico NUMERIC(12, 4) DEFAULT NULL;
    END IF;

    -- positions (crypto)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'cascade_level'
    ) THEN
        ALTER TABLE positions ADD COLUMN cascade_level INT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'cascade_hold'
    ) THEN
        ALTER TABLE positions ADD COLUMN cascade_hold BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'pnl_pico'
    ) THEN
        ALTER TABLE positions ADD COLUMN pnl_pico NUMERIC(20, 8) DEFAULT NULL;
    END IF;
END $$;

-- 3. Create cascada_decisions_log table
CREATE TABLE IF NOT EXISTS cascada_decisions_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id TEXT NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    market_type VARCHAR(20) DEFAULT 'forex',
    cascade_level INT NOT NULL,
    previous_level INT,
    level_advanced BOOLEAN DEFAULT FALSE,
    check_type VARCHAR(30) NOT NULL, -- 'rebote', 'continuacion', 'giveback', 'hold'
    decision VARCHAR(30) NOT NULL,   -- 'CERRAR', 'MANTENER', 'GIVEBACK_CLOSE', 'HOLD'
    cascade_hold BOOLEAN DEFAULT FALSE,
    pnl_current NUMERIC(12, 4),
    pnl_pico NUMERIC(12, 4),
    giveback_pct NUMERIC(6, 2),
    signals JSONB,
    slope_table JSONB,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cascada_decisions_pos ON cascada_decisions_log(position_id);
CREATE INDEX IF NOT EXISTS idx_cascada_decisions_sym ON cascada_decisions_log(symbol);
CREATE INDEX IF NOT EXISTS idx_cascada_decisions_created ON cascada_decisions_log(created_at);

-- 4. Add system_config entries for RADAR and CASCADA
INSERT INTO system_config (key, value, description) VALUES
    ('radar_enabled', 'true'::jsonb, 'Activar bus de señales compartido RADAR'),
    ('radar_slope_ascending_threshold', '0.15'::jsonb, 'Umbral de pendiente ascendente normalizada ATR'),
    ('radar_slope_descending_threshold', '-0.15'::jsonb, 'Umbral de pendiente descendente normalizada ATR'),
    ('radar_slope_lookback_candles', '3'::jsonb, 'Número de velas cerradas para cálculo de pendiente'),
    ('cascada_enabled', 'true'::jsonb, 'Activar gestor de posiciones CASCADA'),
    ('cascada_giveback_threshold_pct', '0.50'::jsonb, 'Umbral de retroceso de PNL pico para forzar cierre (50%)'),
    ('cascada_support_signal_bb_tf', '"15m"'::jsonb, 'Timeframe para señal de apoyo Bollinger'),
    ('cascada_support_signal_hh_tf_n1', '"15m"'::jsonb, 'Timeframe para señal de apoyo HH descendentes en N1'),
    ('cascada_support_signal_hh_tf_n2_n5', '"1h"'::jsonb, 'Timeframe para señal de apoyo HH descendentes en N2 a N5')
ON CONFLICT (key) DO NOTHING;

-- <<< migration_035_radar_cascada.sql <<<


-- >>> migration_036_warrior_playbook_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 036: ROSS CAMERON PLAYBOOK & TRADING EXPERIENCE KNOWLEDGE BASE
-- =========================================================================

-- 1. Tabla de Sesiones Diarias y Contexto de Mentalidad/Gestión
CREATE TABLE IF NOT EXISTS warrior_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trader_name VARCHAR(64) DEFAULT 'Ross Cameron',
    session_date DATE NOT NULL,
    video_title VARCHAR(255) NOT NULL,
    video_url TEXT,
    net_pnl NUMERIC(12, 2) NOT NULL,
    
    -- Contexto Operativo y Mental
    account_mode VARCHAR(64) DEFAULT 'main_account', -- 'main_account', 'small_account', 'split_focus'
    prior_drawdown NUMERIC(12, 2) DEFAULT 0,         -- Ej: -44000
    mental_state TEXT,                               -- Ej: "Racha negativa previa, recuperar disciplina de foco"
    key_mindset_change TEXT,                         -- Ej: "Enfocar solo cuenta grande para no perder velocidad"
    stop_trading_discipline TEXT,                    -- Ej: "Cerrar sesión tras meta, ignorar CZ +140% para no devolver"
    
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Catálogo de Arquetipos de Patrones (Plantillas para el Robot)
CREATE TABLE IF NOT EXISTS warrior_archetypes (
    code VARCHAR(64) PRIMARY KEY,                   -- Ej: 'ROSS_VWAP_BOUNCE_CLEAN'
    name VARCHAR(128) NOT NULL,
    description TEXT,
    ideal_time_window VARCHAR(64),                  -- '08:30-09:30 AM', '09:30-10:30 AM'
    ideal_float_max NUMERIC(12, 2),                 -- Ej: 10000000 (10M shares)
    ideal_price_range NUMERIC(10, 2)[] DEFAULT '{1.50, 15.00}',
    scanner_criteria JSONB NOT NULL,                -- {"min_gap_pct": 20, "min_rvol": 3.0, "running_up": true}
    entry_trigger JSONB NOT NULL,                   -- {"type": "vwap_support", "confirm": "green_candle_rebound"}
    exit_strategy JSONB NOT NULL,                   -- {"type": "scaling_out_into_surges", "max_hold_sec": 180}
    pitfalls_to_avoid TEXT[] DEFAULT '{}',          -- ["200 MA overhead resistance", "High spread dip slippage"]
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Registro de Operaciones Individuales de la Sesión
CREATE TABLE IF NOT EXISTS warrior_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES warrior_sessions(id) ON DELETE CASCADE,
    archetype_code VARCHAR(64) REFERENCES warrior_archetypes(code),
    ticker VARCHAR(16) NOT NULL,
    pnl NUMERIC(12, 2) NOT NULL,
    duration_seconds INT,                           -- Ej: 120 (2 minutos)
    
    -- Variables del Activo al Momento de Operar
    sector VARCHAR(64),
    float_shares NUMERIC(14, 2),
    premarket_gap_pct NUMERIC(8, 2),
    running_surge_pct NUMERIC(8, 2),
    entry_time TIME,
    exit_time TIME,
    
    -- Métricas de Ejecución
    max_shares_held INT,
    avg_entry_price NUMERIC(10, 4),
    avg_exit_price NUMERIC(10, 4),
    peak_unrealized_pnl NUMERIC(12, 2),
    giveback_pnl NUMERIC(12, 2) DEFAULT 0,
    
    -- Lección Clave del Trade
    key_takeaway TEXT,
    raw_transcript_snippet TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Fases Tácticas Secuenciales del Trade (Paso a Paso de la Decisión)
CREATE TABLE IF NOT EXISTS warrior_trade_phases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id UUID REFERENCES warrior_trades(id) ON DELETE CASCADE,
    sequence_order INT NOT NULL,                    -- 1, 2, 3, 4
    phase_type VARCHAR(32) NOT NULL,                -- 'FILTERING', 'ENTRY', 'SCALING_IN', 'SCALING_OUT', 'DIP_REBUY', 'STOPPED_OUT'
    timestamp_or_time_str VARCHAR(32),              -- Ej: "08:50 AM", "Segundo 45"
    price_level NUMERIC(10, 4),
    shares INT,
    
    -- Lógica del Trader
    trigger_observed TEXT NOT NULL,                 -- Ej: "Precio en $8.00 tocando VWAP tras rechazo de 200 MA"
    action_taken TEXT NOT NULL,                     -- Ej: "Comprar 15,000 acciones buscando rebote limpio"
    risk_factor TEXT,                               -- Ej: "Resistencia de 200 MA overhead en $9.00"
    result_outcome TEXT,                            -- Ej: "Disparo inmediato a $9.50, vender bloque completo"
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Reglas de Inferencia en Tiempo Real para el Robot
CREATE TABLE IF NOT EXISTS warrior_bot_action_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    archetype_code VARCHAR(64) REFERENCES warrior_archetypes(code),
    condition_expression JSONB NOT NULL,
    bot_command VARCHAR(64) NOT NULL,               -- 'BLOCK_FIRST_PULLBACK', 'BUY_VWAP_SUPPORT', 'PYRAMID_SCALE_IN', 'HARD_CUT_SLIPPAGE'
    parameters JSONB NOT NULL,
    priority INT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE
);

-- =========================================================================
-- SEED DATA: ARQUETIPOS DE PATRONES DE ROSS CAMERON
-- =========================================================================
INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES
(
    'ROSS_VWAP_BOUNCE_CLEAN',
    'Rebote Limpio en Soporte VWAP',
    'Entrada en el primer toque de VWAP tras un impulso inicial fuerte, evitando comprar micro pullbacks si colisionan con resistencias mayores (como la media móvil de 200 periodos).',
    '09:30-10:15 AM',
    20000000,
    '{2.00, 15.00}',
    '{"min_gain_from_open_pct": 30, "min_rvol": 4.0}',
    '{"type": "vwap_touch", "support_buffer_pct": 1.0, "confirm_rebound": true}',
    '{"type": "quick_rip_exit", "target_pct": 15.0, "sell_into_first_red_5s": true}',
    ARRAY['200 MA overhead resistance', 'Falling knife through VWAP without volume bounce']
),
(
    'ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT',
    'Ruptura de Consolidación sobre VWAP',
    'Acción que tuvo un primer empuje, cayó debajo de VWAP, pero logró recuperarse y construir una base plana justo encima de VWAP. Se entra antes del quiebre de números enteros/medios.',
    '08:45-10:30 AM',
    15000000,
    '{1.50, 12.00}',
    '{"min_volume": 1000000, "base_duration_minutes": 5}',
    '{"type": "anticipate_whole_number", "offset_cents": 0.02, "above_vwap": true}',
    '{"type": "scaling_out_into_surges", "tranches": [0.33, 0.33, 0.34]}',
    ARRAY['Dip buying slippage on widening Level 2 spread', 'Breakout fakeout if volume stalls below key level']
),
(
    'ROSS_RUNNING_UP_PYRAMID',
    'Pirámide Acelerada en Escáner Running Up',
    'Acción con catalizador de volumen masivo (+200%) en escáner de alta velocidad. Se entra con lote inicial y se escala agresivamente (scaling in) conforme rompe niveles cada 10-20 centavos.',
    '08:30-09:45 AM',
    8000000,
    '{1.50, 8.00}',
    '{"running_up_scanner": true, "min_gain_pct": 150, "volume_surge_per_min": 500000}',
    '{"type": "pyramid_scaling_in", "initial_tranche_pct": 30, "add_on_breakouts": [0.10, 0.25, 0.50]}',
    '{"type": "parabolic_climax_dump", "exit_on_first_exhaustion_print": true, "max_trade_seconds": 180}',
    ARRAY['Chasing above whole number with exhausted tape', 'Holding through pullbacks on parabolic moves']
)
ON CONFLICT (code) DO NOTHING;

-- =========================================================================
-- SEED DATA: SESIÓN HISTÓRICA +$72,872.42 (JUNIO 2024 / 2026)
-- =========================================================================
DO $$
DECLARE
    v_session_id UUID;
    v_trade_vwave_id UUID;
    v_trade_svre_id UUID;
    v_trade_gem_id UUID;
BEGIN
    -- 1. Insertar Sesión
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-06-28',
        '+$72,872.42 on 3 Explosive Stocks',
        'https://www.youtube.com/watch?v=warrior_trading_72k_recap',
        72872.42,
        'main_account',
        -44000.00,
        'Racha negativa de dos días consecutivos (-$37k y -$22k); foco disperso entre cuentas.',
        'Eliminó la cuenta pequeña de la vista operativa y enfocó el 100% de capital y atención en la cuenta principal para máxima velocidad.',
        'Se detuvo tras el estallido de GEM. Ignoró otros gappers como CZ (+140%) para blindar los $72k ganados.',
        'Cierre de mes récord superando $500,000 en beneficios acumulados.'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: VWave (+$10,000)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_VWAP_BOUNCE_CLEAN', 'VWave', 10000.00, 300, 'Defensa / Aeroespacial', 12000000, 80.0,
        8.00, 9.50, 'Dejar pasar el primer micro-pullback si choca contra la 200 MA. Comprar el rebote limpio en el VWAP.'
    ) RETURNING id INTO v_trade_vwave_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_vwave_id, 1, 'FILTERING', 9.00, 'Precio rozando la media de 200 periodos (200 MA) en $9.00', 'Omitir el primer micro-pullback', '200 MA actúa como techo de resistencia infranqueable en primer intento', 'Evitó quedar atrapado en la trampa'),
    (v_trade_vwave_id, 2, 'ENTRY', 8.00, 'Precio retrocede a $8.00 tocando con precisión la línea del VWAP', 'Comprar soporte VWAP buscando rebote limpio', 'Riesgo de perforación bajista con stop por debajo de $7.80', 'Rebote comprador inmediato con fuerte absorción'),
    (v_trade_vwave_id, 3, 'EXIT', 9.50, 'El precio explota a $9.50 y el Level 2 muestra primer volumen vendedor pesado', 'Vender posición completa', 'Volumen de compradores comenzando a decrecer', 'Asegura +$10,000 limpios y se retira (la acción cayó más tarde)');

    -- 3. Operación 2: SVRE (+$16,000 Netos)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, peak_unrealized_pnl, giveback_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT', 'SVRE', 16000.00, 480, 'Tecnología / Auto', 6500000, 120.0,
        6.98, 8.50, 18800.00, 2800.00, 'Entrada anticipada en $6.98 antes de romper $7.00 sobre VWAP. Alerta: no sobreoperar dips con spread abierto en Level 2.'
    ) RETURNING id INTO v_trade_svre_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_svre_id, 1, 'FILTERING', 8.33, 'Subida inicial a $3.66 luego sube a $8.33 y cae bajo VWAP perdiendo impulso', 'Omitir primeros picos caóticos', 'Acción sobreextendida con riesgo de trampa', 'Esperó consolidación real'),
    (v_trade_svre_id, 2, 'ENTRY', 6.98, 'La acción se monta por encima del VWAP y lateraliza construyendo base', 'Entrar en $6.98 anticipando la ruptura de los $7.00 psicológicos', 'Resistencia psicológica en $7.00', 'Ruptura explosiva con velocidad'),
    (v_trade_svre_id, 3, 'SCALING_OUT', 8.50, 'Precio alcanza tramos de $7.50, $8.00 y $8.50 a $9.00', 'Vender parcialmente en cada impulso', 'Sobreextensión en temporalidad corta', 'Amarra hasta +$18,800 de ganancia no realizada'),
    (v_trade_svre_id, 4, 'DIP_REBUY', 8.00, 'Intento de recompra en retroceso con 10,000 acciones a $8.00', 'Compra en dip', 'Spread amplio en Level 2 provoca slippage al activarse el Stop Loss', 'Devuelve $2,800 a $3,000, cerrando la acción con +$16,000 netos');

    -- 4. Operación 3: GEM (+$46,000 en 2 Minutos)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        max_shares_held, avg_entry_price, avg_exit_price, peak_unrealized_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_RUNNING_UP_PYRAMID', 'GEM', 46000.00, 120, 'Gaming / Entretenimiento', 4200000, 230.0,
        60000, 3.88, 5.58, 48000.00, 'Piramidación agresiva (Scaling In) en acción con aceleración masiva de volumen (>230%). Salida en el clímax parabólico.'
    ) RETURNING id INTO v_trade_gem_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_gem_id, 1, 'FILTERING', 3.57, 'Alerta del escáner "Running Up" a las 8:50 AM cotizando en $3.57 (+230%)', 'Identificar catalizador de volumen extremo', 'Volatilidad salvaje y spreads rápidos', 'Disparo de alerta para entrada inmediata'),
    (v_trade_gem_id, 2, 'ENTRY', 3.70, 'Confirmación de aceleración de cinta Level 2', 'Comprar bloque inicial de 15,000 acciones a $3.70', 'Riesgo de falso breakout', 'La cinta se llena de órdenes verdes a mercado'),
    (v_trade_gem_id, 3, 'SCALING_IN', 3.90, 'El precio vuela y rompe $3.80, $3.95 y $4.00', 'Añadir agresivamente paquetes de 10,000 a 15,000 acciones', 'Aumento de exposición monetaria', 'Construye posición gigante de 45,000 a 60,000 acciones con precio promedio ponderado $3.88'),
    (v_trade_gem_id, 4, 'SCALING_OUT', 4.20, 'Primera aceleración por encima de $4.00', 'Tomar primer beneficio parcial en $4.20', 'Proteger centro de costo', 'Garantiza ganancias base'),
    (v_trade_gem_id, 5, 'SCALING_IN', 5.00, 'Ruptura masiva del nivel entero de $5.00', 'Añade último paquete para la estocada final', 'Riesgo de clímax parabólico inminente', 'Disparo directo hacia $5.50-$5.66'),
    (v_trade_gem_id, 6, 'EXIT', 5.58, 'El precio alcanza $5.58 (el HOD fue $5.66) y aparecen muros de venta en Level 2', 'Vender el bloque principal en el pico', 'Volumen de clímax alcanzado', '+$46,000 asegurados en menos de 120 segundos');

END $$;

-- <<< migration_036_warrior_playbook_kb.sql <<<


-- >>> migration_037_warrior_cold_market_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 037: SEED DATA CASO "DON'T MAKE IT WORSE!" (MERCADO ROJO/FRÍO)
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_COLD_MARKET_DEFENSE',
    'Defensa Activa en Mercado Frío/Rojo (Don''t Make It Worse)',
    'Protocolo de reducción de riesgo y preservación de capital cuando S&P 500 y Nasdaq están en rojo y los breakouts de pequeña capitalización no tienen seguimiento. Tamaño al 25%-33%, prohibidas recompras en techos planos y salida inmediata ante mechas de rechazo.',
    '08:30-09:45 AM',
    10000000,
    '{1.50, 10.00}',
    '{"macro_cold": true, "size_reduction_pct": 70}',
    '{"type": "conservative_dip_only", "require_clean_support": true}',
    '{"type": "quick_rip_scalp", "target_pct": 5.0, "hard_stop_on_topping_tail": true}',
    ARRAY['Overtrading / Revenge trading', 'Buying flat-top squeezes in cold tape', 'Holding through topping tail candles', 'Trading thickly traded or illiquid reverse splits']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_pcla_id UUID;
    v_trade_nwe_id UUID;
    v_trade_davi_id UUID;
BEGIN
    -- 1. Insertar Sesión "Don't Make It Worse!"
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-08-29',
        'Don''t Make It Worse!',
        'https://www.youtube.com/watch?v=warrior_dont_make_it_worse',
        -1516.16,
        'main_account',
        0.00,
        'Mercado frío, lento y errático en pre-mercado con S&P 500 y Nasdaq en rojo; breakouts sin volumen de continuación.',
        'Regla de oro: ''Don''t Make It Worse!''. Reducir el tamaño de posición al 25%-33% del estándar. Aceptar una pérdida pequeña (-$1,500) y proteger el capital en vez de entrar en espiral de venganza arriesgando -$15,000 o -$20,000.',
        'Cerrar la sesión temprano tras detectar mechas de rechazo superiores (topping tails) y giros violentos (jackknife). Dejar de operar antes de que el mercado abra si no hay confirmación.',
        'Sesión defensiva maestra. Operó PCLA (-$1,000), NWE (-$798.16) y DAVI (+$282). Descartó con disciplina NCPL (thickly traded), AXG (sin volumen tras split) y DAIC (noticia positiva pero en cinta roja).'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: PCLA (-$1,000)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'PCLA', -1000.00, 180, 'Salud / Farmacéutica Japonesa', 8000000, 40.0,
        3.20, 3.05, 'En mercado frío, el intento de curl back hacia máximos falló con vela de rechazo superior (topping tail candle). Liquidación defensiva rápida.'
    ) RETURNING id INTO v_trade_pcla_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_pcla_id, 1, 'ENTRY', 3.20, 'Intento de recuperación (curl back) hacia los máximos de la mañana tras rebote inicial.', 'Comprar con tamaño de posición reducido para buscar continuación alcista.', 'Mercado macro frío sin volumen de seguimiento institucional.', 'El precio sube brevemente pero no logra absorber las ventas en la zona alta.'),
    (v_trade_pcla_id, 2, 'EXIT', 3.05, 'Aparición de mecha superior de rechazo (topping tail candle) y reanudación de volumen vendedor.', 'Cortar la posición con pérdida controlada de -$1,000 para no agrandar el daño.', 'Desplome posterior si se intenta aguantar (hope mode).', 'Pérdida pequeña asumida con disciplina; la acción siguió cayendo.');

    -- 3. Operación 2: NWE (-$798.16)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, peak_unrealized_pnl, giveback_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'NWE', -798.16, 360, 'Energía / Utilities', 14000000, 35.0,
        7.25, 7.10, 350.00, 1148.16, 'Ruptura de compresión en techo plano (flat top squeeze) en $7.33 provocó un doble techo y rechazo violento (jackknife). Prohibido forzar recompras en techos en mercado rojo.'
    ) RETURNING id INTO v_trade_nwe_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_nwe_id, 1, 'ENTRY', 6.90, 'Retroceso hacia soporte (buy the dip) tras subida matutina.', 'Comprar en el dip con lote pequeño.', 'Mercado sin momentum.', 'Pequeño rebote aprovechado para tomar una ganancia modesta.'),
    (v_trade_nwe_id, 2, 'ENTRY', 7.25, 'Consolidación en la zona alta buscando compresión alcista (squeeze through flat top) en $7.33.', 'Volver a comprar en la ruptura anticipada.', 'Doble techo en resistencia sin fuerza de ruptura.', 'Fallo rotundo en $7.33 formando doble techo.'),
    (v_trade_nwe_id, 3, 'EXIT', 7.10, 'Rechazo alcista violento en forma de navaja (jackknife reversal) desplomándose en segundos.', 'Venta inmediata para frenar la sangría.', 'Deslizamiento si no se corta en el acto.', 'Devolvió la ganancia inicial y cerró con -$798.16 USD de pérdida neta.');

    -- 4. Operación 3: DAVI (+$282)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, peak_unrealized_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'DAVI', 282.00, 120, 'Tecnología / Inteligencia Artificial', 7200000, 50.0,
        4.05, 4.15, 350.00, 'En mercado frío, si una ruptura ($4.00) no tiene aceleración inmediata, tomar ganancias mínimas (+3% a +5%) y salir rápido.'
    ) RETURNING id INTO v_trade_davi_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_davi_id, 1, 'ENTRY', 4.05, 'Noticia positiva y gráfico diario similar al patrón de la acción AI, rompiendo los $4.00 buscando $5.00-$6.00.', 'Entrar con lote moderado en la rotura de $4.00.', 'Mercado general apagado que frena los seguimientos.', 'Pequeño empuje comprador hacia $4.15-$4.20.'),
    (v_trade_davi_id, 2, 'EXIT', 4.15, 'Falta de volumen y desaceleración inmediata de la cinta.', 'Vender para asegurar +$282 USD de ganancia parcial.', 'Reversión a negativo si se espera el target optimista de $5.00.', 'Aseguró pequeña ganancia y evitó quedar atrapado en la posterior caída.');

END $$;

-- <<< migration_037_warrior_cold_market_kb.sql <<<


-- >>> migration_038_warrior_monday_squeeze_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 038: SEED DATA CASO "MONDAY SHORT SQUEEZE +225%" (+$9,671.43 USD)
-- MNDR (+225% No News Squeeze), GIXI (+100% Sympathy Wave), WFFF, MEDS
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_NO_NEWS_PARABOLIC_SQUEEZE',
    'Short Squeeze Parabólico Sin Noticias (MNDR Pattern)',
    'Disparo parabólico vertical (>150%-225%) en pre-mercado sin catalizador fundamental. Entrada en micro pullback anticipando números enteros con Stop corto fijo de 10-15 centavos debido a que el soporte estructural está alejado.',
    '07:30-09:15 AM',
    6000000,
    '{0.80, 5.00}',
    '{"no_news_squeeze": true, "surge_min_pct": 100, "tight_micro_stop": true}',
    '{"type": "micro_pullback_whole_number", "anticipation": true}',
    '{"type": "fast_acceleration_exit", "trailing_stop": true, "exit_on_topping_tail": true}',
    ARRAY['Using distant structural support as stop loss (causes massive loss)', 'Entering before 7:15 AM without volume', 'Chasing topping tails above whole number']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_mndr_id UUID;
    v_trade_gixi_id UUID;
    v_trade_wfff_id UUID;
    v_trade_meds_id UUID;
BEGIN
    -- 1. Insertar Sesión de Lunes
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-10-14',
        'Crazy +225% Short Squeeze on Monday Morning! (+$9,671.43)',
        'https://www.youtube.com/watch?v=warrior_monday_squeeze_mndr',
        9671.43,
        'main_account',
        0.00,
        'Apertura de semana (lunes temprano). Enfoque en capturar el lead gapper que despierte el apetito del mercado.',
        'Dominar el Efecto Ola de Simpatía (Sympathy Wave) y la regla de Stop Corto en soporte lejano: Cuando un short squeeze (MNDR +225%) no tiene noticias, el soporte estructural queda a kilómetros ($1.12 vs $1.70); se DEBE usar un stop mental ceñido de 10 a 15 centavos. El calor generado por el primer corredor activa compras masivas en las siguientes acciones con noticias frescas (GIXI a las 7:32 AM).',
        'Cerró la jornada con 5 operaciones ganadoras de 6 (+9,671.43). La única pérdida fue MEDS (-$1,200) a las 7:00 AM por precipitarse antes de que el mercado tuviera volumen real.',
        'Sesión maestra de lunes: MNDR (+$1,300), GIXI (+$7,289.43), WFFF (+$2,282), MEDS (-$1,200). Monitoreó además CLWT, DCX e YMAT.'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: MNDR (+$1,300)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_NEWS_PARABOLIC_SQUEEZE', 'MNDR', 1300.00, 300, 'Tecnología / Salud Móvil (Singapur)', 3200000, 225.0,
        1.70, 2.35, 'Short Squeeze parabólico sin noticias (+225%). Entrada en micro pullback a $1.70 anticipando quiebre de $2.00 con Stop corto de 10-15 centavos porque el soporte real ($1.12) estaba muy lejos.'
    ) RETURNING id INTO v_trade_mndr_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_mndr_id, 1, 'FILTERING', 1.12, 'Disparo vertical inicial desde $0.92 hasta $1.12 y $1.50 sin noticias fundamentales.', 'Dejar pasar el primer tramo parabólico desordenado.', 'Perseguir precios sin soporte definido.', 'Esperó a que el gráfico marcara el primer retroceso ordenado.'),
    (v_trade_mndr_id, 2, 'ENTRY', 1.70, 'Micro pullback limpio alrededor de $1.70 formando bandera antes de la barrera psicológica de $2.00.', 'Comprar en $1.70 anticipando la ruptura de los $2.00.', 'Soporte técnico real muy abajo ($1.12); ratio R:R inviable si se usa soporte base.', 'Aplicó regla de Stop corto fijo de 10-15 centavos (stop en $1.58-$1.60).'),
    (v_trade_mndr_id, 3, 'SCALING_OUT', 2.25, 'Ruptura de los $2.00 disparando con violencia hacia $2.25 y $2.40.', 'Vender bloques parciales en la aceleración.', 'Volatilidad extrema.', 'Aseguró ganancias iniciales sin riesgo.'),
    (v_trade_mndr_id, 4, 'EXIT', 2.50, 'Precio alcanza pico en $2.57-$2.90 y aparecen velas con mechas superiores (topping tail).', 'Venta total asegurando +$1,300 USD de beneficio conservador.', 'Reversión inmediata de short squeeze sin noticias.', 'Salida perfecta antes de la posterior consolidación pesada.');

    -- 3. Operación 2: GIXI (+$7,289.43)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_NEWS_PARABOLIC_SQUEEZE', 'GIXI', 7289.43, 420, 'Tecnología (Israel)', 4800000, 100.0,
        2.10, 3.40, 'Operación estrella de la sesión. Catalizador de noticia a las 7:32 AM montado sobre la ola de simpatía (Sympathy Wave) que MNDR despertó en el mercado.'
    ) RETURNING id INTO v_trade_gixi_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_gixi_id, 1, 'ENTRY', 2.10, 'Noticia publicada a las 7:32 AM con el mercado caliente por la subida de MNDR.', 'Entrar con alta convicción aprovechando el apetito comprador desatado.', 'Falso breakout de pre-mercado.', 'Explosión del 100% hacia $3.50+ con volumen arrollador.'),
    (v_trade_gixi_id, 2, 'EXIT', 3.40, 'Desaceleración de cinta en $3.50 con absorción institucional.', 'Venta en la cima asegurando más de +$7,000 USD de ganancia.', 'Toma masiva de beneficios de pre-mercado.', 'Trade más lucrativo de la jornada matutina.');

    -- 4. Operación 3: WFFF (+$2,282.00)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT', 'WFFF', 2282.00, 240, 'Consumo / Agro (Malasia)', 5100000, 45.0,
        12.50, 13.80, 'Operación de continuidad ingresando en $12.50 y tomando beneficios rápidos en la zona de $13.70-$14.69.'
    ) RETURNING id INTO v_trade_wfff_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_wfff_id, 1, 'ENTRY', 12.50, 'Continuación alcista tras consolidación con volumen ascendente.', 'Entrar en $12.50 buscando impulso hacia $14.00.', 'Precio nominal alto ($12+).', 'Disparo limpio hacia $13.70-$14.69.'),
    (v_trade_wfff_id, 2, 'EXIT', 13.80, 'Llegada a resistencia en $14.00.', 'Tomar ganancias rápidas asegurando +$2,282 USD.', 'Rechazo en números enteros.', 'Ganancia capturada con precisión.');

    -- 5. Operación 4: MEDS (-$1,200.00)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'MEDS', -1200.00, 180, 'Salud / Farmacia', 6000000, 25.0,
        3.40, 3.15, 'Única pérdida del día (-$1,200). Comprar patrón curl a las 7:00 AM es prematuro porque el mercado carece de volumen a esa hora.'
    ) RETURNING id INTO v_trade_meds_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_meds_id, 1, 'ENTRY', 3.40, 'Intento de recuperación (curl) a las 7:00 AM.', 'Comprar anticipando continuidad.', 'Hora excesivamente temprana (7:00 AM) con volumen desértico.', 'Falta total de compradores; el precio se desinfló.'),
    (v_trade_meds_id, 2, 'EXIT', 3.15, 'Ruptura a la baja sin soporte de cinta.', 'Cerrar con stop loss defensivo perdiendo -$1,200.', 'Desplome si no se respeta el stop.', 'Pérdida asumida; evitó un castigo mayor.');

END $$;

-- <<< migration_038_warrior_monday_squeeze_kb.sql <<<


-- >>> migration_039_warrior_no_trade_discipline_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 039: SEED DATA CASO "THREE STOCKS ARE UP OVER 100% RIGHT NOW" ($0.00 USD)
-- PROTOCOLO NO TRADE DAY / PRESERVACIÓN EN DRAWDOWN: SIQ, APUS, MI
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_NO_TRADE_DISCIPLINE',
    'Disciplina de Cero Operaciones (No Trade Day / Sidelines)',
    'Protocolo de preservación absoluta de capital y paciencia en drawdown. Cuando activos de +100% muestran movimientos agotados de madrugada (4 AM), rechazos continuos en resistencia sin riesgo claro o paradas por volatilidad (halts), la decisión correcta es quedarse al margen ($0 USD).',
    'Pre-Market / Toda la sesión',
    10000000,
    '{1.00, 20.00}',
    '{"no_trade_filter": true, "require_definable_risk": true}',
    '{"type": "no_entry_stay_on_sidelines", "require_strict_rr": true}',
    '{"type": "capital_preservation", "target_pct": 0.0}',
    ARRAY['Chasing exhausted 4:00 AM spikes', 'Trading choppy resistance without clear stop', 'Buying single-minute spikes into volatility halts', 'Boredom trading during drawdowns']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_siq_id UUID;
    v_trade_apus_id UUID;
    v_trade_mi_id UUID;
BEGIN
    -- 1. Insertar Sesión No Trade Day
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-10-07',
        'Three Stocks Are Up Over 100% RIGHT NOW (No Trade Day - $0.00)',
        'https://www.youtube.com/watch?v=warrior_three_stocks_100_no_trade',
        0.00,
        'main_account',
        -25000.00,
        'Transmisión desde furgoneta Mercedes Sprinter equipada con Starlink. En periodo de recuperación de pérdidas (drawdown); enfoque estricto en paciencia y no forzar operaciones.',
        'Saber cuándo NO operar (''No Trade Day'') es una habilidad táctica maestra. Si una acción subió a las 4 AM y dejó mechas de rechazo (SIQ), si muestra falsas rupturas sin riesgo definible (APUS), o si explota en 1 vela sin noticias y entra en halts (MI), la decisión correcta es quedarse al margen ($0 USD). Preservar el capital en drawdown es la máxima prioridad.',
        'Cero operaciones ejecutadas (0 trades, $0.00 PnL). A pesar de haber 3 acciones con subidas superiores al 100%, ninguna ofreció una relación riesgo/beneficio ejecutable.',
        'Análisis exhaustivo de 3 corredores de más de 100%: SIQ (+900% SPAC), APUS (+100%), MI (+220% en 1m). Todas descartadas con disciplina quirúrgica.'
    ) RETURNING id INTO v_session_id;

    -- 2. Emisora 1: SIQ ($0.00 PnL)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_TRADE_DISCIPLINE', 'SIQ', 0.00, 0, 'SPAC Merger / Wise Space Holdings', 2500000, 900.0,
        0.00, 0.00, 'Subió de $1.80 a $18.37 a las 4:00 AM tras fusión SPAC. A las 6:45 AM el movimiento ya había ocurrido y dejó una vela con enorme mecha superior (topping tail). Descartada por impulso agotado y salida en pánico.'
    ) RETURNING id INTO v_trade_siq_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_siq_id, 1, 'FILTERING', 18.37, 'Explosión de $1.80-$3.60 a $18.37 a las 4:00 AM con fusión de SPAC del viernes.', 'No perseguir en pre-mercado tardío.', 'El 90% del impulso ocurrió antes de que abrieran los escáneres principales; volumen vendedor masivo posterior.', 'Aparición de vela de rechazo superior extrema (topping tail); el precio colapsó.');

    -- 3. Emisora 2: APUS ($0.00 PnL)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_TRADE_DISCIPLINE', 'APUS', 0.00, 0, 'Small Cap Momentum', 4200000, 100.0,
        0.00, 0.00, 'Subió de $3.40 a $7.00 respaldada por noticia de 3:40 AM. Aunque formó hombro-cabeza-hombro invertido, marcó continuas mechas de rechazo y falsas rupturas en resistencia sin riesgo claro. Descartada por riesgo no definible.'
    ) RETURNING id INTO v_trade_apus_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_apus_id, 1, 'FILTERING', 6.40, 'Impulso hacia $6.40 y $7.00 con noticia a las 3:40 AM; patrón HCH invertido en gráfico de 5m.', 'Evaluar punto de entrada en resistencia.', 'Múltiples mechas superiores de rechazo y amagos de falso breakout.', 'Imposibilidad de colocar un stop loss con buena relación riesgo/beneficio. Se descartó la compra.');

    -- 4. Emisora 3: MI ($0.00 PnL)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_TRADE_DISCIPLINE', 'MI', 0.00, 0, 'Micro Cap Volatility', 1800000, 220.0,
        0.00, 0.00, 'Disparo vertical de $1.25 a $4.00 en una sola vela de 1 minuto sin noticias. Entró de inmediato en suspensiones por volatilidad (volatility halts), imposibilitando la gestión del riesgo.'
    ) RETURNING id INTO v_trade_mi_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_mi_id, 1, 'FILTERING', 4.00, 'Aparición súbita en el escáner saltando de $1.25 a $4.00 en 60 segundos sin catalizador fundamental.', 'Monitorear Level 2 sin colocar orden.', 'Entrada en múltiples paradas por volatilidad (halts) que congelan la orden y exponen a gaps bajistas.', 'Descartada totalmente; durante un halt el stop loss no se ejecuta y el riesgo es incontrolable.');

END $$;

-- <<< migration_039_warrior_no_trade_discipline_kb.sql <<<


-- >>> migration_040_warrior_wild_card_friday_amod_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 040: SEED DATA CASO "WILD CARD FRIDAY SHORT SQUEEZE (+300% AMOD)" (+$700.00 USD)
-- PATRÓN BANDERA 5M SOBRE 9 EMA (AMOD) Y FILTRO CURL HACIA DOBLE TECHO (TN)
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_5M_BULL_FLAG_9EMA',
    'Bandera Alcista de 5 Minutos sobre 9 EMA (AMOD Pattern)',
    'Patrón de scalping de alta probabilidad en corredores de alto volumen (+200-300%). Requiere MACD positivo; se entra en la bandera de consolidación de 5 minutos apoyada en la media móvil exponencial de 9 períodos (9 EMA) buscando el quiebre hacia número redondo ($4.00) con toma de beneficios inmediata.',
    '08:45-10:15 AM (Pre-Market y Apertura)',
    15000000,
    '{1.50, 8.00}',
    '{"min_volume": 20000000, "surge_min_pct": 100, "require_positive_macd": true}',
    '{"type": "5m_bull_flag_9ema", "target_round_number": true}',
    '{"type": "fast_scalp_whole_number", "target_cents": 0.10, "trailing_stop": false}',
    ARRAY['Buying when MACD is negative', 'Buying curls into double tops in cold tape', 'Holding past whole numbers instead of taking quick scalp']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_tn_id UUID;
    v_trade_amod_id UUID;
BEGIN
    -- 1. Insertar Sesión Wild Card Friday
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-10-18',
        'Wild Card Friday Short Squeeze (+300% AMOD) - (+$700.00)',
        'https://www.youtube.com/watch?v=warrior_wild_card_friday_amod',
        700.00,
        'main_account',
        -18000.00,
        'Sesión de pre-mercado y apertura de un viernes (''Wild Card Friday''), cerrando una semana difícil/roja en un mercado frío. Prioridad: disciplina y protección de capital.',
        'Gestión de tamaño a un décimo (1/10): Debido a la baja liquidez y alta tasa de rechazos, reducir el lote al 10% del estándar blinda el capital. En AMOD descartó compras iniciales por MACD negativo y esperó pacientemente la bandera de 5 minutos sobre la 9 EMA hacia los $4.00. Terminar en verde (+ $700) compensando una pérdida previa cierra la semana en positivo.',
        'Cerró el viernes con ganancia neta verde tras compensar la pérdida de TN (-$1,179.48) con la ganancia de AMOD (+$1,800.00). Mantuvo la disciplina de no sobreoperar en viernes frío.',
        'Sesión Wild Card Friday: AMOD (+300%, +$1,800.00), TN (-$1,179.48). Tamaño de posición al 1/10 (10%).'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: TN (-$1,179.48 USD)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'TN', -1179.48, 150, 'Penny Stocks / Nano Cap', 3500000, 15.0,
        0.61, 0.49, 'Comprar patrón curl hacia doble techo en $0.61 solo subió a $0.70 antes de sufrir un rechazo violento. Salida defensiva perdiendo 11 centavos por acción (-$1,179.48).'
    ) RETURNING id INTO v_trade_tn_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_tn_id, 1, 'ENTRY', 0.61, 'Intento de curvatura alcista (curl) hacia la zona de doble techo.', 'Comprar 10,000 acciones a $0.61.', 'Resistencia pesada en doble techo y mercado frío sin seguimiento.', 'El precio avanzó apenas a $0.70 y fue rechazado con violencia.'),
    (v_trade_tn_id, 2, 'EXIT', 0.49, 'Pérdida rápida de soporte con volumen vendedor.', 'Ejecutar stop loss vendiendo en la caída.', 'Colapso a mínimos si se aguanta la posición.', 'Pérdida de -$1,179.48 USD asumida con disciplina.');

    -- 3. Operación 2: AMOD (+$1,800.00 USD)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_5M_BULL_FLAG_9EMA', 'AMOD', 1800.00, 120, 'Tecnología / Short Squeeze (+300%)', 4500000, 300.0,
        3.90, 4.00, 'Disparo de +300% con más de 100M de volumen. Descartó compras con MACD negativo. Esperó bandera alcista de 5m sobre la 9 EMA y ejecutó scalping rápido hacia la cifra redonda de $4.00 asegurando +$1,800 USD en segundos.'
    ) RETURNING id INTO v_trade_amod_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_amod_id, 1, 'FILTERING', 3.20, 'Impulso temprano con lecturas de MACD negativo / divergencia.', 'Descartar compras iniciales hasta que el indicador confirme alineación.', 'Falso breakout con momentum negativo.', 'Evitó quedar atrapado en el retroceso inicial.'),
    (v_trade_amod_id, 2, 'ENTRY', 3.90, 'Bandera alcista de 5 minutos consolidando sobre la 9 EMA preparándose para quebrar $4.00.', 'Entrar con scalping rápido de 20,000 acciones en la ruptura.', 'Rechazo en número entero psicológico.', 'Aceleración inmediata directa a $4.00.'),
    (v_trade_amod_id, 3, 'EXIT', 4.00, 'Toque del precio en la cifra redonda de $4.00.', 'Venta relámpago de las 20,000 acciones para capturar 10 centavos por acción.', 'Pausa por volatilidad o rechazo en $4.00.', '+$1,800 USD asegurados en segundos; jornada cerrada en verde.');

END $$;

-- <<< migration_040_warrior_wild_card_friday_amod_kb.sql <<<


-- >>> migration_041_scanner_velocity.sql >>>
-- =========================================================================
-- MIGRACIÓN 041: RANKING POR VELOCIDAD (Velocity Score) + GATE DEL PLAYBOOK
-- Claves en stocks_config editables desde Settings / STOCKS
-- =========================================================================
INSERT INTO stocks_config (key, value, description, category, editable, value_type)
VALUES
  ('scanner_min_change_pct',  '3.0',    'Variación mínima del día (%) para aparecer en el escáner de velocidad', 'scanner', true, 'number'),
  ('scanner_min_rvol',        '1.5',    'RVOL mínimo para aparecer en el escáner de velocidad',                  'scanner', true, 'number'),
  ('scanner_min_adx_5m',      '20',     'ADX 5m mínimo (fuerza de tendencia corta)',                             'scanner', true, 'number'),
  ('scanner_min_volume',      '300000', 'Volumen mínimo acumulado del día',                                      'scanner', true, 'number'),
  ('scanner_min_dp5m_pct',    '0.0',    'ΔP mínimo últimos 5 min (%). Bajo este valor + EMA3<EMA9 5m = descendente', 'scanner', true, 'number'),
  ('velocity_w_rvol',         '0.35',   'Peso RVOL en Velocity Score',                                           'scanner', true, 'number'),
  ('velocity_w_adx',          '0.25',   'Peso ADX 5m en Velocity Score',                                         'scanner', true, 'number'),
  ('velocity_w_dp5m',         '0.30',   'Peso ΔP 5m en Velocity Score',                                          'scanner', true, 'number'),
  ('velocity_w_vol',          '0.10',   'Peso Volumen en Velocity Score',                                        'scanner', true, 'number'),
  ('scanner_refresh_seconds', '60',     'Refresco del ranking por velocidad (segundos, mínimo 15)',              'scanner', true, 'number'),
  ('velocity_gate_min_score', '10',     'Velocity Score mínimo vigente al momento del disparo de compra',        'scalping', true, 'number'),
  ('playbook_gate_mode',      'enforce','Gate Playbook Ross Cameron antes de comprar: enforce (bloquea+tamaño) | observe (solo registra)', 'scalping', true, 'select'),
  ('cold_market_spy_pct',     '-0.3',   'Mercado frío si SPY o QQQ varían menos que este % en el día',           'scalping', true, 'number')
ON CONFLICT (key) DO NOTHING;

-- <<< migration_041_scanner_velocity.sql <<<


-- =========================================================================
-- ETRADE -> OKLANTRADE SUPABASE CONSOLIDATED MIGRATIONS BUNDLE (CLEAN UTF-8)
-- Proyecto: iriotnsoauqrfsjbqyyp (oklantrade-collab's Org)
-- =========================================================================

-- >>> ARCHIVO: backend/migration_014_signals_log.sql >>>
-- MIGRATION 014: signals_log — Auditoría de señales detectadas (Ejecutadas y Bloqueadas)
-- eTrade v4 | Marzo 2026

CREATE TABLE IF NOT EXISTS signals_log (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(30) NOT NULL,
    direction       VARCHAR(10) NOT NULL,
    rule_code       VARCHAR(10),
    price           NUMERIC(20,8),
    score_final     NUMERIC(8,4),
    acted_on        BOOLEAN DEFAULT false,
    reason_skip     TEXT,
    metadata        JSONB,
    detected_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_log_symbol_ts ON signals_log(symbol, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_log_acted_on ON signals_log(acted_on, detected_at DESC);

-- Habilitar tiempo real
-- ALTER PUBLICATION supabase_realtime ADD TABLE signals_log;

-- <<< FIN: backend/migration_014_signals_log.sql <<<

-- >>> ARCHIVO: backend/migration_033_halcon_centinela.sql >>>
-- ============================================================
-- HALCÓN CENTINELA — Database Migration
-- eTrade v5.0 — Gestor de Cierre Proactivo Multi-Timeframe
-- ============================================================

-- ── 1. Tabla de log de scores HALCÓN ──
-- Registra cada evaluación del motor de scoring por posición
CREATE TABLE IF NOT EXISTS halcon_scores_log (
    id BIGSERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_profile TEXT DEFAULT 'TENDENCIA_SOSTENIDA',
    market_type TEXT DEFAULT 'forex',
    -- Scores por capa (antes de ajustes de régimen)
    score_1d INT DEFAULT 0,
    score_4h INT DEFAULT 0,
    score_15m INT DEFAULT 0,
    score_5m INT DEFAULT 0,
    score_1m INT DEFAULT 0,
    -- Ajustes RSI por capa
    rsi_adj_1d INT DEFAULT 0,
    rsi_adj_4h INT DEFAULT 0,
    rsi_adj_15m INT DEFAULT 0,
    rsi_adj_5m INT DEFAULT 0,
    -- Régimen y compresión
    regime TEXT,
    regime_adx FLOAT,
    compression_index FLOAT,
    compression_timeframe TEXT,
    fib_zone INT,
    fib_multiplier FLOAT DEFAULT 1.0,
    -- Resultado final
    score_final FLOAT NOT NULL,
    semaforo TEXT NOT NULL,
    decision TEXT NOT NULL,
    squeeze_active BOOLEAN DEFAULT FALSE,
    volume_confirmed BOOLEAN,
    -- Ejecución
    executed BOOLEAN DEFAULT FALSE,
    pnl_at_evaluation FLOAT,
    -- Detalle completo (JSON)
    detail JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_halcon_scores_position ON halcon_scores_log(position_id);
CREATE INDEX IF NOT EXISTS idx_halcon_scores_symbol ON halcon_scores_log(symbol);
CREATE INDEX IF NOT EXISTS idx_halcon_scores_created ON halcon_scores_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_halcon_scores_decision ON halcon_scores_log(decision);

-- ── 2. Tabla de decisiones CENTINELA ──
-- Registra cada decisión de cierre/mantener con contexto completo
CREATE TABLE IF NOT EXISTS centinela_decisions_log (
    id BIGSERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market_type TEXT DEFAULT 'forex',
    decision TEXT NOT NULL,
    reason TEXT,
    score_final FLOAT,
    pnl_at_decision FLOAT,
    entry_profile TEXT,
    -- ORÁCULO
    oraculo_override BOOLEAN DEFAULT FALSE,
    oraculo_event TEXT,
    -- Ejecución
    executed BOOLEAN DEFAULT FALSE,
    execution_result JSONB,
    -- Arbitraje
    blocked_by TEXT,
    closing_in_progress_set BOOLEAN DEFAULT FALSE,
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_centinela_decisions_position ON centinela_decisions_log(position_id);
CREATE INDEX IF NOT EXISTS idx_centinela_decisions_symbol ON centinela_decisions_log(symbol);
CREATE INDEX IF NOT EXISTS idx_centinela_decisions_created ON centinela_decisions_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_centinela_decisions_executed ON centinela_decisions_log(executed);

-- ── 3. Cache de eventos económicos para ORÁCULO ──
CREATE TABLE IF NOT EXISTS oraculo_events (
    id BIGSERIAL PRIMARY KEY,
    event_name TEXT NOT NULL,
    country TEXT,
    currency TEXT,
    impact TEXT NOT NULL,
    event_datetime TIMESTAMPTZ NOT NULL,
    is_global BOOLEAN DEFAULT FALSE,
    -- Pausa
    trading_paused_symbols TEXT[],
    pause_start TIMESTAMPTZ,
    pause_end TIMESTAMPTZ,
    -- Estado
    processed BOOLEAN DEFAULT FALSE,
    actions_taken JSONB,
    -- Sync
    source TEXT DEFAULT 'finnhub',
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    -- Evitar duplicados
    UNIQUE(event_name, event_datetime)
);

CREATE INDEX IF NOT EXISTS idx_oraculo_events_datetime ON oraculo_events(event_datetime);
CREATE INDEX IF NOT EXISTS idx_oraculo_events_currency ON oraculo_events(currency);
CREATE INDEX IF NOT EXISTS idx_oraculo_events_processed ON oraculo_events(processed);

-- ── 4. Estado CENTINELA por posición ──
-- Almacena el estado de la máquina de estados de cada posición
CREATE TABLE IF NOT EXISTS centinela_position_state (
    position_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    market_type TEXT DEFAULT 'forex',
    -- Estado CENTINELA
    halcon_state TEXT DEFAULT 'NEUTRAL',
    closing_in_progress BOOLEAN DEFAULT FALSE,
    -- Historial
    last_close_action_at TIMESTAMPTZ,
    last_score_final FLOAT,
    last_semaforo TEXT,
    last_decision TEXT,
    -- Cooldown
    cooldown_until TIMESTAMPTZ,
    -- Perfil
    entry_profile TEXT DEFAULT 'TENDENCIA_SOSTENIDA',
    partial_closed_pct FLOAT DEFAULT 0,
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_centinela_state_symbol ON centinela_position_state(symbol);
CREATE INDEX IF NOT EXISTS idx_centinela_state_closing ON centinela_position_state(closing_in_progress);

-- ── 5. Configuración HALCÓN en system_config ──
-- Inserta parámetros configurables como pares clave-valor
INSERT INTO system_config (key, value)
VALUES 
    ('halcon_enabled', 'true'),
    ('halcon_min_profit_usd', '1.0'),
    ('halcon_partial_close_pct', '0.50'),
    ('halcon_adx_range_threshold', '15'),
    ('halcon_adx_trend_threshold', '30'),
    ('halcon_compression_threshold', '0.15'),
    ('halcon_volume_multiplier', '1.3'),
    ('halcon_volume_lookback', '10'),
    ('halcon_atr_pct_threshold', '0.008'),
    ('halcon_rsi_extreme_low', '20'),
    ('halcon_rsi_extreme_high', '80'),
    ('halcon_rsi_extreme_points', '25'),
    ('halcon_rsi_divergence_points', '35'),
    ('halcon_ema_proximity_pct', '0.15'),
    ('halcon_oraculo_enabled', 'true'),
    ('halcon_oraculo_pre_event_min', '60'),
    ('halcon_oraculo_post_event_min', '60'),
    ('halcon_oraculo_close_pnl_threshold', '-5.0'),
    ('halcon_oraculo_bracket_sl_floor', '-8.0'),
    ('halcon_oraculo_calendar_sync_min', '60')
ON CONFLICT (key) DO NOTHING;

-- ── 6. Retención automática — limpiar logs antiguos (>30 días) ──
-- Puede ejecutarse como cron job o scheduled task
-- DELETE FROM halcon_scores_log WHERE created_at < NOW() - INTERVAL '30 days';
-- DELETE FROM centinela_decisions_log WHERE created_at < NOW() - INTERVAL '30 days';
-- DELETE FROM oraculo_events WHERE event_datetime < NOW() - INTERVAL '7 days';

-- <<< FIN: backend/migration_033_halcon_centinela.sql <<<

-- >>> ARCHIVO: backend/migration_034_rebote_aduana.sql >>>
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

-- <<< FIN: backend/migration_034_rebote_aduana.sql <<<

-- >>> ARCHIVO: backend/migration_035_radar_cascada.sql >>>
-- ============================================================================
-- migration_035_radar_cascada.sql
-- RADAR and CASCADA modules integration schema updates
-- ============================================================================

-- 1. Add 'origen' column to forex_positions and positions (if not already present)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'origen'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN origen VARCHAR(50) DEFAULT 'STANDARD';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'origen'
    ) THEN
        ALTER TABLE positions ADD COLUMN origen VARCHAR(50) DEFAULT 'STANDARD';
    END IF;
END $$;

-- 2. Add CASCADA state columns to forex_positions and positions
DO $$
BEGIN
    -- forex_positions
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'cascade_level'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN cascade_level INT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'cascade_hold'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN cascade_hold BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'pnl_pico'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN pnl_pico NUMERIC(12, 4) DEFAULT NULL;
    END IF;

    -- positions (crypto)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'cascade_level'
    ) THEN
        ALTER TABLE positions ADD COLUMN cascade_level INT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'cascade_hold'
    ) THEN
        ALTER TABLE positions ADD COLUMN cascade_hold BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'pnl_pico'
    ) THEN
        ALTER TABLE positions ADD COLUMN pnl_pico NUMERIC(20, 8) DEFAULT NULL;
    END IF;
END $$;

-- 3. Create cascada_decisions_log table
CREATE TABLE IF NOT EXISTS cascada_decisions_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id TEXT NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    market_type VARCHAR(20) DEFAULT 'forex',
    cascade_level INT NOT NULL,
    previous_level INT,
    level_advanced BOOLEAN DEFAULT FALSE,
    check_type VARCHAR(30) NOT NULL, -- 'rebote', 'continuacion', 'giveback', 'hold'
    decision VARCHAR(30) NOT NULL,   -- 'CERRAR', 'MANTENER', 'GIVEBACK_CLOSE', 'HOLD'
    cascade_hold BOOLEAN DEFAULT FALSE,
    pnl_current NUMERIC(12, 4),
    pnl_pico NUMERIC(12, 4),
    giveback_pct NUMERIC(6, 2),
    signals JSONB,
    slope_table JSONB,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cascada_decisions_pos ON cascada_decisions_log(position_id);
CREATE INDEX IF NOT EXISTS idx_cascada_decisions_sym ON cascada_decisions_log(symbol);
CREATE INDEX IF NOT EXISTS idx_cascada_decisions_created ON cascada_decisions_log(created_at);

-- 4. Add system_config entries for RADAR and CASCADA
INSERT INTO system_config (key, value, description) VALUES
    ('radar_enabled', 'true'::jsonb, 'Activar bus de señales compartido RADAR'),
    ('radar_slope_ascending_threshold', '0.15'::jsonb, 'Umbral de pendiente ascendente normalizada ATR'),
    ('radar_slope_descending_threshold', '-0.15'::jsonb, 'Umbral de pendiente descendente normalizada ATR'),
    ('radar_slope_lookback_candles', '3'::jsonb, 'Número de velas cerradas para cálculo de pendiente'),
    ('cascada_enabled', 'true'::jsonb, 'Activar gestor de posiciones CASCADA'),
    ('cascada_giveback_threshold_pct', '0.50'::jsonb, 'Umbral de retroceso de PNL pico para forzar cierre (50%)'),
    ('cascada_support_signal_bb_tf', '"15m"'::jsonb, 'Timeframe para señal de apoyo Bollinger'),
    ('cascada_support_signal_hh_tf_n1', '"15m"'::jsonb, 'Timeframe para señal de apoyo HH descendentes en N1'),
    ('cascada_support_signal_hh_tf_n2_n5', '"1h"'::jsonb, 'Timeframe para señal de apoyo HH descendentes en N2 a N5')
ON CONFLICT (key) DO NOTHING;

-- <<< FIN: backend/migration_035_radar_cascada.sql <<<

-- >>> ARCHIVO: backend/migration_036_warrior_playbook_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 036: ROSS CAMERON PLAYBOOK & TRADING EXPERIENCE KNOWLEDGE BASE
-- =========================================================================

-- 1. Tabla de Sesiones Diarias y Contexto de Mentalidad/Gestión
CREATE TABLE IF NOT EXISTS warrior_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trader_name VARCHAR(64) DEFAULT 'Ross Cameron',
    session_date DATE NOT NULL,
    video_title VARCHAR(255) NOT NULL,
    video_url TEXT,
    net_pnl NUMERIC(12, 2) NOT NULL,
    
    -- Contexto Operativo y Mental
    account_mode VARCHAR(64) DEFAULT 'main_account', -- 'main_account', 'small_account', 'split_focus'
    prior_drawdown NUMERIC(12, 2) DEFAULT 0,         -- Ej: -44000
    mental_state TEXT,                               -- Ej: "Racha negativa previa, recuperar disciplina de foco"
    key_mindset_change TEXT,                         -- Ej: "Enfocar solo cuenta grande para no perder velocidad"
    stop_trading_discipline TEXT,                    -- Ej: "Cerrar sesión tras meta, ignorar CZ +140% para no devolver"
    
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Catálogo de Arquetipos de Patrones (Plantillas para el Robot)
CREATE TABLE IF NOT EXISTS warrior_archetypes (
    code VARCHAR(64) PRIMARY KEY,                   -- Ej: 'ROSS_VWAP_BOUNCE_CLEAN'
    name VARCHAR(128) NOT NULL,
    description TEXT,
    ideal_time_window VARCHAR(64),                  -- '08:30-09:30 AM', '09:30-10:30 AM'
    ideal_float_max NUMERIC(12, 2),                 -- Ej: 10000000 (10M shares)
    ideal_price_range NUMERIC(10, 2)[] DEFAULT '{1.50, 15.00}',
    scanner_criteria JSONB NOT NULL,                -- {"min_gap_pct": 20, "min_rvol": 3.0, "running_up": true}
    entry_trigger JSONB NOT NULL,                   -- {"type": "vwap_support", "confirm": "green_candle_rebound"}
    exit_strategy JSONB NOT NULL,                   -- {"type": "scaling_out_into_surges", "max_hold_sec": 180}
    pitfalls_to_avoid TEXT[] DEFAULT '{}',          -- ["200 MA overhead resistance", "High spread dip slippage"]
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Registro de Operaciones Individuales de la Sesión
CREATE TABLE IF NOT EXISTS warrior_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES warrior_sessions(id) ON DELETE CASCADE,
    archetype_code VARCHAR(64) REFERENCES warrior_archetypes(code),
    ticker VARCHAR(16) NOT NULL,
    pnl NUMERIC(12, 2) NOT NULL,
    duration_seconds INT,                           -- Ej: 120 (2 minutos)
    
    -- Variables del Activo al Momento de Operar
    sector VARCHAR(64),
    float_shares NUMERIC(14, 2),
    premarket_gap_pct NUMERIC(8, 2),
    running_surge_pct NUMERIC(8, 2),
    entry_time TIME,
    exit_time TIME,
    
    -- Métricas de Ejecución
    max_shares_held INT,
    avg_entry_price NUMERIC(10, 4),
    avg_exit_price NUMERIC(10, 4),
    peak_unrealized_pnl NUMERIC(12, 2),
    giveback_pnl NUMERIC(12, 2) DEFAULT 0,
    
    -- Lección Clave del Trade
    key_takeaway TEXT,
    raw_transcript_snippet TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Fases Tácticas Secuenciales del Trade (Paso a Paso de la Decisión)
CREATE TABLE IF NOT EXISTS warrior_trade_phases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id UUID REFERENCES warrior_trades(id) ON DELETE CASCADE,
    sequence_order INT NOT NULL,                    -- 1, 2, 3, 4
    phase_type VARCHAR(32) NOT NULL,                -- 'FILTERING', 'ENTRY', 'SCALING_IN', 'SCALING_OUT', 'DIP_REBUY', 'STOPPED_OUT'
    timestamp_or_time_str VARCHAR(32),              -- Ej: "08:50 AM", "Segundo 45"
    price_level NUMERIC(10, 4),
    shares INT,
    
    -- Lógica del Trader
    trigger_observed TEXT NOT NULL,                 -- Ej: "Precio en $8.00 tocando VWAP tras rechazo de 200 MA"
    action_taken TEXT NOT NULL,                     -- Ej: "Comprar 15,000 acciones buscando rebote limpio"
    risk_factor TEXT,                               -- Ej: "Resistencia de 200 MA overhead en $9.00"
    result_outcome TEXT,                            -- Ej: "Disparo inmediato a $9.50, vender bloque completo"
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Reglas de Inferencia en Tiempo Real para el Robot
CREATE TABLE IF NOT EXISTS warrior_bot_action_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    archetype_code VARCHAR(64) REFERENCES warrior_archetypes(code),
    condition_expression JSONB NOT NULL,
    bot_command VARCHAR(64) NOT NULL,               -- 'BLOCK_FIRST_PULLBACK', 'BUY_VWAP_SUPPORT', 'PYRAMID_SCALE_IN', 'HARD_CUT_SLIPPAGE'
    parameters JSONB NOT NULL,
    priority INT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE
);

-- =========================================================================
-- SEED DATA: ARQUETIPOS DE PATRONES DE ROSS CAMERON
-- =========================================================================
INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES
(
    'ROSS_VWAP_BOUNCE_CLEAN',
    'Rebote Limpio en Soporte VWAP',
    'Entrada en el primer toque de VWAP tras un impulso inicial fuerte, evitando comprar micro pullbacks si colisionan con resistencias mayores (como la media móvil de 200 periodos).',
    '09:30-10:15 AM',
    20000000,
    '{2.00, 15.00}',
    '{"min_gain_from_open_pct": 30, "min_rvol": 4.0}',
    '{"type": "vwap_touch", "support_buffer_pct": 1.0, "confirm_rebound": true}',
    '{"type": "quick_rip_exit", "target_pct": 15.0, "sell_into_first_red_5s": true}',
    ARRAY['200 MA overhead resistance', 'Falling knife through VWAP without volume bounce']
),
(
    'ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT',
    'Ruptura de Consolidación sobre VWAP',
    'Acción que tuvo un primer empuje, cayó debajo de VWAP, pero logró recuperarse y construir una base plana justo encima de VWAP. Se entra antes del quiebre de números enteros/medios.',
    '08:45-10:30 AM',
    15000000,
    '{1.50, 12.00}',
    '{"min_volume": 1000000, "base_duration_minutes": 5}',
    '{"type": "anticipate_whole_number", "offset_cents": 0.02, "above_vwap": true}',
    '{"type": "scaling_out_into_surges", "tranches": [0.33, 0.33, 0.34]}',
    ARRAY['Dip buying slippage on widening Level 2 spread', 'Breakout fakeout if volume stalls below key level']
),
(
    'ROSS_RUNNING_UP_PYRAMID',
    'Pirámide Acelerada en Escáner Running Up',
    'Acción con catalizador de volumen masivo (+200%) en escáner de alta velocidad. Se entra con lote inicial y se escala agresivamente (scaling in) conforme rompe niveles cada 10-20 centavos.',
    '08:30-09:45 AM',
    8000000,
    '{1.50, 8.00}',
    '{"running_up_scanner": true, "min_gain_pct": 150, "volume_surge_per_min": 500000}',
    '{"type": "pyramid_scaling_in", "initial_tranche_pct": 30, "add_on_breakouts": [0.10, 0.25, 0.50]}',
    '{"type": "parabolic_climax_dump", "exit_on_first_exhaustion_print": true, "max_trade_seconds": 180}',
    ARRAY['Chasing above whole number with exhausted tape', 'Holding through pullbacks on parabolic moves']
)
ON CONFLICT (code) DO NOTHING;

-- =========================================================================
-- SEED DATA: SESIÓN HISTÓRICA +$72,872.42 (JUNIO 2024 / 2026)
-- =========================================================================
DO $$
DECLARE
    v_session_id UUID;
    v_trade_vwave_id UUID;
    v_trade_svre_id UUID;
    v_trade_gem_id UUID;
BEGIN
    -- 1. Insertar Sesión
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-06-28',
        '+$72,872.42 on 3 Explosive Stocks',
        'https://www.youtube.com/watch?v=warrior_trading_72k_recap',
        72872.42,
        'main_account',
        -44000.00,
        'Racha negativa de dos días consecutivos (-$37k y -$22k); foco disperso entre cuentas.',
        'Eliminó la cuenta pequeña de la vista operativa y enfocó el 100% de capital y atención en la cuenta principal para máxima velocidad.',
        'Se detuvo tras el estallido de GEM. Ignoró otros gappers como CZ (+140%) para blindar los $72k ganados.',
        'Cierre de mes récord superando $500,000 en beneficios acumulados.'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: VWave (+$10,000)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_VWAP_BOUNCE_CLEAN', 'VWave', 10000.00, 300, 'Defensa / Aeroespacial', 12000000, 80.0,
        8.00, 9.50, 'Dejar pasar el primer micro-pullback si choca contra la 200 MA. Comprar el rebote limpio en el VWAP.'
    ) RETURNING id INTO v_trade_vwave_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_vwave_id, 1, 'FILTERING', 9.00, 'Precio rozando la media de 200 periodos (200 MA) en $9.00', 'Omitir el primer micro-pullback', '200 MA actúa como techo de resistencia infranqueable en primer intento', 'Evitó quedar atrapado en la trampa'),
    (v_trade_vwave_id, 2, 'ENTRY', 8.00, 'Precio retrocede a $8.00 tocando con precisión la línea del VWAP', 'Comprar soporte VWAP buscando rebote limpio', 'Riesgo de perforación bajista con stop por debajo de $7.80', 'Rebote comprador inmediato con fuerte absorción'),
    (v_trade_vwave_id, 3, 'EXIT', 9.50, 'El precio explota a $9.50 y el Level 2 muestra primer volumen vendedor pesado', 'Vender posición completa', 'Volumen de compradores comenzando a decrecer', 'Asegura +$10,000 limpios y se retira (la acción cayó más tarde)');

    -- 3. Operación 2: SVRE (+$16,000 Netos)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, peak_unrealized_pnl, giveback_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT', 'SVRE', 16000.00, 480, 'Tecnología / Auto', 6500000, 120.0,
        6.98, 8.50, 18800.00, 2800.00, 'Entrada anticipada en $6.98 antes de romper $7.00 sobre VWAP. Alerta: no sobreoperar dips con spread abierto en Level 2.'
    ) RETURNING id INTO v_trade_svre_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_svre_id, 1, 'FILTERING', 8.33, 'Subida inicial a $3.66 luego sube a $8.33 y cae bajo VWAP perdiendo impulso', 'Omitir primeros picos caóticos', 'Acción sobreextendida con riesgo de trampa', 'Esperó consolidación real'),
    (v_trade_svre_id, 2, 'ENTRY', 6.98, 'La acción se monta por encima del VWAP y lateraliza construyendo base', 'Entrar en $6.98 anticipando la ruptura de los $7.00 psicológicos', 'Resistencia psicológica en $7.00', 'Ruptura explosiva con velocidad'),
    (v_trade_svre_id, 3, 'SCALING_OUT', 8.50, 'Precio alcanza tramos de $7.50, $8.00 y $8.50 a $9.00', 'Vender parcialmente en cada impulso', 'Sobreextensión en temporalidad corta', 'Amarra hasta +$18,800 de ganancia no realizada'),
    (v_trade_svre_id, 4, 'DIP_REBUY', 8.00, 'Intento de recompra en retroceso con 10,000 acciones a $8.00', 'Compra en dip', 'Spread amplio en Level 2 provoca slippage al activarse el Stop Loss', 'Devuelve $2,800 a $3,000, cerrando la acción con +$16,000 netos');

    -- 4. Operación 3: GEM (+$46,000 en 2 Minutos)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        max_shares_held, avg_entry_price, avg_exit_price, peak_unrealized_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_RUNNING_UP_PYRAMID', 'GEM', 46000.00, 120, 'Gaming / Entretenimiento', 4200000, 230.0,
        60000, 3.88, 5.58, 48000.00, 'Piramidación agresiva (Scaling In) en acción con aceleración masiva de volumen (>230%). Salida en el clímax parabólico.'
    ) RETURNING id INTO v_trade_gem_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_gem_id, 1, 'FILTERING', 3.57, 'Alerta del escáner "Running Up" a las 8:50 AM cotizando en $3.57 (+230%)', 'Identificar catalizador de volumen extremo', 'Volatilidad salvaje y spreads rápidos', 'Disparo de alerta para entrada inmediata'),
    (v_trade_gem_id, 2, 'ENTRY', 3.70, 'Confirmación de aceleración de cinta Level 2', 'Comprar bloque inicial de 15,000 acciones a $3.70', 'Riesgo de falso breakout', 'La cinta se llena de órdenes verdes a mercado'),
    (v_trade_gem_id, 3, 'SCALING_IN', 3.90, 'El precio vuela y rompe $3.80, $3.95 y $4.00', 'Añadir agresivamente paquetes de 10,000 a 15,000 acciones', 'Aumento de exposición monetaria', 'Construye posición gigante de 45,000 a 60,000 acciones con precio promedio ponderado $3.88'),
    (v_trade_gem_id, 4, 'SCALING_OUT', 4.20, 'Primera aceleración por encima de $4.00', 'Tomar primer beneficio parcial en $4.20', 'Proteger centro de costo', 'Garantiza ganancias base'),
    (v_trade_gem_id, 5, 'SCALING_IN', 5.00, 'Ruptura masiva del nivel entero de $5.00', 'Añade último paquete para la estocada final', 'Riesgo de clímax parabólico inminente', 'Disparo directo hacia $5.50-$5.66'),
    (v_trade_gem_id, 6, 'EXIT', 5.58, 'El precio alcanza $5.58 (el HOD fue $5.66) y aparecen muros de venta en Level 2', 'Vender el bloque principal en el pico', 'Volumen de clímax alcanzado', '+$46,000 asegurados en menos de 120 segundos');

END $$;

-- <<< FIN: backend/migration_036_warrior_playbook_kb.sql <<<

-- >>> ARCHIVO: backend/migration_037_warrior_cold_market_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 037: SEED DATA CASO "DON'T MAKE IT WORSE!" (MERCADO ROJO/FRÍO)
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_COLD_MARKET_DEFENSE',
    'Defensa Activa en Mercado Frío/Rojo (Don''t Make It Worse)',
    'Protocolo de reducción de riesgo y preservación de capital cuando S&P 500 y Nasdaq están en rojo y los breakouts de pequeña capitalización no tienen seguimiento. Tamaño al 25%-33%, prohibidas recompras en techos planos y salida inmediata ante mechas de rechazo.',
    '08:30-09:45 AM',
    10000000,
    '{1.50, 10.00}',
    '{"macro_cold": true, "size_reduction_pct": 70}',
    '{"type": "conservative_dip_only", "require_clean_support": true}',
    '{"type": "quick_rip_scalp", "target_pct": 5.0, "hard_stop_on_topping_tail": true}',
    ARRAY['Overtrading / Revenge trading', 'Buying flat-top squeezes in cold tape', 'Holding through topping tail candles', 'Trading thickly traded or illiquid reverse splits']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_pcla_id UUID;
    v_trade_nwe_id UUID;
    v_trade_davi_id UUID;
BEGIN
    -- 1. Insertar Sesión "Don't Make It Worse!"
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-08-29',
        'Don''t Make It Worse!',
        'https://www.youtube.com/watch?v=warrior_dont_make_it_worse',
        -1516.16,
        'main_account',
        0.00,
        'Mercado frío, lento y errático en pre-mercado con S&P 500 y Nasdaq en rojo; breakouts sin volumen de continuación.',
        'Regla de oro: ''Don''t Make It Worse!''. Reducir el tamaño de posición al 25%-33% del estándar. Aceptar una pérdida pequeña (-$1,500) y proteger el capital en vez de entrar en espiral de venganza arriesgando -$15,000 o -$20,000.',
        'Cerrar la sesión temprano tras detectar mechas de rechazo superiores (topping tails) y giros violentos (jackknife). Dejar de operar antes de que el mercado abra si no hay confirmación.',
        'Sesión defensiva maestra. Operó PCLA (-$1,000), NWE (-$798.16) y DAVI (+$282). Descartó con disciplina NCPL (thickly traded), AXG (sin volumen tras split) y DAIC (noticia positiva pero en cinta roja).'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: PCLA (-$1,000)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'PCLA', -1000.00, 180, 'Salud / Farmacéutica Japonesa', 8000000, 40.0,
        3.20, 3.05, 'En mercado frío, el intento de curl back hacia máximos falló con vela de rechazo superior (topping tail candle). Liquidación defensiva rápida.'
    ) RETURNING id INTO v_trade_pcla_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_pcla_id, 1, 'ENTRY', 3.20, 'Intento de recuperación (curl back) hacia los máximos de la mañana tras rebote inicial.', 'Comprar con tamaño de posición reducido para buscar continuación alcista.', 'Mercado macro frío sin volumen de seguimiento institucional.', 'El precio sube brevemente pero no logra absorber las ventas en la zona alta.'),
    (v_trade_pcla_id, 2, 'EXIT', 3.05, 'Aparición de mecha superior de rechazo (topping tail candle) y reanudación de volumen vendedor.', 'Cortar la posición con pérdida controlada de -$1,000 para no agrandar el daño.', 'Desplome posterior si se intenta aguantar (hope mode).', 'Pérdida pequeña asumida con disciplina; la acción siguió cayendo.');

    -- 3. Operación 2: NWE (-$798.16)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, peak_unrealized_pnl, giveback_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'NWE', -798.16, 360, 'Energía / Utilities', 14000000, 35.0,
        7.25, 7.10, 350.00, 1148.16, 'Ruptura de compresión en techo plano (flat top squeeze) en $7.33 provocó un doble techo y rechazo violento (jackknife). Prohibido forzar recompras en techos en mercado rojo.'
    ) RETURNING id INTO v_trade_nwe_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_nwe_id, 1, 'ENTRY', 6.90, 'Retroceso hacia soporte (buy the dip) tras subida matutina.', 'Comprar en el dip con lote pequeño.', 'Mercado sin momentum.', 'Pequeño rebote aprovechado para tomar una ganancia modesta.'),
    (v_trade_nwe_id, 2, 'ENTRY', 7.25, 'Consolidación en la zona alta buscando compresión alcista (squeeze through flat top) en $7.33.', 'Volver a comprar en la ruptura anticipada.', 'Doble techo en resistencia sin fuerza de ruptura.', 'Fallo rotundo en $7.33 formando doble techo.'),
    (v_trade_nwe_id, 3, 'EXIT', 7.10, 'Rechazo alcista violento en forma de navaja (jackknife reversal) desplomándose en segundos.', 'Venta inmediata para frenar la sangría.', 'Deslizamiento si no se corta en el acto.', 'Devolvió la ganancia inicial y cerró con -$798.16 USD de pérdida neta.');

    -- 4. Operación 3: DAVI (+$282)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, peak_unrealized_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'DAVI', 282.00, 120, 'Tecnología / Inteligencia Artificial', 7200000, 50.0,
        4.05, 4.15, 350.00, 'En mercado frío, si una ruptura ($4.00) no tiene aceleración inmediata, tomar ganancias mínimas (+3% a +5%) y salir rápido.'
    ) RETURNING id INTO v_trade_davi_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_davi_id, 1, 'ENTRY', 4.05, 'Noticia positiva y gráfico diario similar al patrón de la acción AI, rompiendo los $4.00 buscando $5.00-$6.00.', 'Entrar con lote moderado en la rotura de $4.00.', 'Mercado general apagado que frena los seguimientos.', 'Pequeño empuje comprador hacia $4.15-$4.20.'),
    (v_trade_davi_id, 2, 'EXIT', 4.15, 'Falta de volumen y desaceleración inmediata de la cinta.', 'Vender para asegurar +$282 USD de ganancia parcial.', 'Reversión a negativo si se espera el target optimista de $5.00.', 'Aseguró pequeña ganancia y evitó quedar atrapado en la posterior caída.');

END $$;

-- <<< FIN: backend/migration_037_warrior_cold_market_kb.sql <<<

-- >>> ARCHIVO: backend/migration_038_warrior_monday_squeeze_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 038: SEED DATA CASO "MONDAY SHORT SQUEEZE +225%" (+$9,671.43 USD)
-- MNDR (+225% No News Squeeze), GIXI (+100% Sympathy Wave), WFFF, MEDS
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_NO_NEWS_PARABOLIC_SQUEEZE',
    'Short Squeeze Parabólico Sin Noticias (MNDR Pattern)',
    'Disparo parabólico vertical (>150%-225%) en pre-mercado sin catalizador fundamental. Entrada en micro pullback anticipando números enteros con Stop corto fijo de 10-15 centavos debido a que el soporte estructural está alejado.',
    '07:30-09:15 AM',
    6000000,
    '{0.80, 5.00}',
    '{"no_news_squeeze": true, "surge_min_pct": 100, "tight_micro_stop": true}',
    '{"type": "micro_pullback_whole_number", "anticipation": true}',
    '{"type": "fast_acceleration_exit", "trailing_stop": true, "exit_on_topping_tail": true}',
    ARRAY['Using distant structural support as stop loss (causes massive loss)', 'Entering before 7:15 AM without volume', 'Chasing topping tails above whole number']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_mndr_id UUID;
    v_trade_gixi_id UUID;
    v_trade_wfff_id UUID;
    v_trade_meds_id UUID;
BEGIN
    -- 1. Insertar Sesión de Lunes
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-10-14',
        'Crazy +225% Short Squeeze on Monday Morning! (+$9,671.43)',
        'https://www.youtube.com/watch?v=warrior_monday_squeeze_mndr',
        9671.43,
        'main_account',
        0.00,
        'Apertura de semana (lunes temprano). Enfoque en capturar el lead gapper que despierte el apetito del mercado.',
        'Dominar el Efecto Ola de Simpatía (Sympathy Wave) y la regla de Stop Corto en soporte lejano: Cuando un short squeeze (MNDR +225%) no tiene noticias, el soporte estructural queda a kilómetros ($1.12 vs $1.70); se DEBE usar un stop mental ceñido de 10 a 15 centavos. El calor generado por el primer corredor activa compras masivas en las siguientes acciones con noticias frescas (GIXI a las 7:32 AM).',
        'Cerró la jornada con 5 operaciones ganadoras de 6 (+9,671.43). La única pérdida fue MEDS (-$1,200) a las 7:00 AM por precipitarse antes de que el mercado tuviera volumen real.',
        'Sesión maestra de lunes: MNDR (+$1,300), GIXI (+$7,289.43), WFFF (+$2,282), MEDS (-$1,200). Monitoreó además CLWT, DCX e YMAT.'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: MNDR (+$1,300)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_NEWS_PARABOLIC_SQUEEZE', 'MNDR', 1300.00, 300, 'Tecnología / Salud Móvil (Singapur)', 3200000, 225.0,
        1.70, 2.35, 'Short Squeeze parabólico sin noticias (+225%). Entrada en micro pullback a $1.70 anticipando quiebre de $2.00 con Stop corto de 10-15 centavos porque el soporte real ($1.12) estaba muy lejos.'
    ) RETURNING id INTO v_trade_mndr_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_mndr_id, 1, 'FILTERING', 1.12, 'Disparo vertical inicial desde $0.92 hasta $1.12 y $1.50 sin noticias fundamentales.', 'Dejar pasar el primer tramo parabólico desordenado.', 'Perseguir precios sin soporte definido.', 'Esperó a que el gráfico marcara el primer retroceso ordenado.'),
    (v_trade_mndr_id, 2, 'ENTRY', 1.70, 'Micro pullback limpio alrededor de $1.70 formando bandera antes de la barrera psicológica de $2.00.', 'Comprar en $1.70 anticipando la ruptura de los $2.00.', 'Soporte técnico real muy abajo ($1.12); ratio R:R inviable si se usa soporte base.', 'Aplicó regla de Stop corto fijo de 10-15 centavos (stop en $1.58-$1.60).'),
    (v_trade_mndr_id, 3, 'SCALING_OUT', 2.25, 'Ruptura de los $2.00 disparando con violencia hacia $2.25 y $2.40.', 'Vender bloques parciales en la aceleración.', 'Volatilidad extrema.', 'Aseguró ganancias iniciales sin riesgo.'),
    (v_trade_mndr_id, 4, 'EXIT', 2.50, 'Precio alcanza pico en $2.57-$2.90 y aparecen velas con mechas superiores (topping tail).', 'Venta total asegurando +$1,300 USD de beneficio conservador.', 'Reversión inmediata de short squeeze sin noticias.', 'Salida perfecta antes de la posterior consolidación pesada.');

    -- 3. Operación 2: GIXI (+$7,289.43)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_NEWS_PARABOLIC_SQUEEZE', 'GIXI', 7289.43, 420, 'Tecnología (Israel)', 4800000, 100.0,
        2.10, 3.40, 'Operación estrella de la sesión. Catalizador de noticia a las 7:32 AM montado sobre la ola de simpatía (Sympathy Wave) que MNDR despertó en el mercado.'
    ) RETURNING id INTO v_trade_gixi_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_gixi_id, 1, 'ENTRY', 2.10, 'Noticia publicada a las 7:32 AM con el mercado caliente por la subida de MNDR.', 'Entrar con alta convicción aprovechando el apetito comprador desatado.', 'Falso breakout de pre-mercado.', 'Explosión del 100% hacia $3.50+ con volumen arrollador.'),
    (v_trade_gixi_id, 2, 'EXIT', 3.40, 'Desaceleración de cinta en $3.50 con absorción institucional.', 'Venta en la cima asegurando más de +$7,000 USD de ganancia.', 'Toma masiva de beneficios de pre-mercado.', 'Trade más lucrativo de la jornada matutina.');

    -- 4. Operación 3: WFFF (+$2,282.00)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT', 'WFFF', 2282.00, 240, 'Consumo / Agro (Malasia)', 5100000, 45.0,
        12.50, 13.80, 'Operación de continuidad ingresando en $12.50 y tomando beneficios rápidos en la zona de $13.70-$14.69.'
    ) RETURNING id INTO v_trade_wfff_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_wfff_id, 1, 'ENTRY', 12.50, 'Continuación alcista tras consolidación con volumen ascendente.', 'Entrar en $12.50 buscando impulso hacia $14.00.', 'Precio nominal alto ($12+).', 'Disparo limpio hacia $13.70-$14.69.'),
    (v_trade_wfff_id, 2, 'EXIT', 13.80, 'Llegada a resistencia en $14.00.', 'Tomar ganancias rápidas asegurando +$2,282 USD.', 'Rechazo en números enteros.', 'Ganancia capturada con precisión.');

    -- 5. Operación 4: MEDS (-$1,200.00)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'MEDS', -1200.00, 180, 'Salud / Farmacia', 6000000, 25.0,
        3.40, 3.15, 'Única pérdida del día (-$1,200). Comprar patrón curl a las 7:00 AM es prematuro porque el mercado carece de volumen a esa hora.'
    ) RETURNING id INTO v_trade_meds_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_meds_id, 1, 'ENTRY', 3.40, 'Intento de recuperación (curl) a las 7:00 AM.', 'Comprar anticipando continuidad.', 'Hora excesivamente temprana (7:00 AM) con volumen desértico.', 'Falta total de compradores; el precio se desinfló.'),
    (v_trade_meds_id, 2, 'EXIT', 3.15, 'Ruptura a la baja sin soporte de cinta.', 'Cerrar con stop loss defensivo perdiendo -$1,200.', 'Desplome si no se respeta el stop.', 'Pérdida asumida; evitó un castigo mayor.');

END $$;

-- <<< FIN: backend/migration_038_warrior_monday_squeeze_kb.sql <<<

-- >>> ARCHIVO: backend/migration_039_warrior_no_trade_discipline_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 039: SEED DATA CASO "THREE STOCKS ARE UP OVER 100% RIGHT NOW" ($0.00 USD)
-- PROTOCOLO NO TRADE DAY / PRESERVACIÓN EN DRAWDOWN: SIQ, APUS, MI
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_NO_TRADE_DISCIPLINE',
    'Disciplina de Cero Operaciones (No Trade Day / Sidelines)',
    'Protocolo de preservación absoluta de capital y paciencia en drawdown. Cuando activos de +100% muestran movimientos agotados de madrugada (4 AM), rechazos continuos en resistencia sin riesgo claro o paradas por volatilidad (halts), la decisión correcta es quedarse al margen ($0 USD).',
    'Pre-Market / Toda la sesión',
    10000000,
    '{1.00, 20.00}',
    '{"no_trade_filter": true, "require_definable_risk": true}',
    '{"type": "no_entry_stay_on_sidelines", "require_strict_rr": true}',
    '{"type": "capital_preservation", "target_pct": 0.0}',
    ARRAY['Chasing exhausted 4:00 AM spikes', 'Trading choppy resistance without clear stop', 'Buying single-minute spikes into volatility halts', 'Boredom trading during drawdowns']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_siq_id UUID;
    v_trade_apus_id UUID;
    v_trade_mi_id UUID;
BEGIN
    -- 1. Insertar Sesión No Trade Day
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-10-07',
        'Three Stocks Are Up Over 100% RIGHT NOW (No Trade Day - $0.00)',
        'https://www.youtube.com/watch?v=warrior_three_stocks_100_no_trade',
        0.00,
        'main_account',
        -25000.00,
        'Transmisión desde furgoneta Mercedes Sprinter equipada con Starlink. En periodo de recuperación de pérdidas (drawdown); enfoque estricto en paciencia y no forzar operaciones.',
        'Saber cuándo NO operar (''No Trade Day'') es una habilidad táctica maestra. Si una acción subió a las 4 AM y dejó mechas de rechazo (SIQ), si muestra falsas rupturas sin riesgo definible (APUS), o si explota en 1 vela sin noticias y entra en halts (MI), la decisión correcta es quedarse al margen ($0 USD). Preservar el capital en drawdown es la máxima prioridad.',
        'Cero operaciones ejecutadas (0 trades, $0.00 PnL). A pesar de haber 3 acciones con subidas superiores al 100%, ninguna ofreció una relación riesgo/beneficio ejecutable.',
        'Análisis exhaustivo de 3 corredores de más de 100%: SIQ (+900% SPAC), APUS (+100%), MI (+220% en 1m). Todas descartadas con disciplina quirúrgica.'
    ) RETURNING id INTO v_session_id;

    -- 2. Emisora 1: SIQ ($0.00 PnL)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_TRADE_DISCIPLINE', 'SIQ', 0.00, 0, 'SPAC Merger / Wise Space Holdings', 2500000, 900.0,
        0.00, 0.00, 'Subió de $1.80 a $18.37 a las 4:00 AM tras fusión SPAC. A las 6:45 AM el movimiento ya había ocurrido y dejó una vela con enorme mecha superior (topping tail). Descartada por impulso agotado y salida en pánico.'
    ) RETURNING id INTO v_trade_siq_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_siq_id, 1, 'FILTERING', 18.37, 'Explosión de $1.80-$3.60 a $18.37 a las 4:00 AM con fusión de SPAC del viernes.', 'No perseguir en pre-mercado tardío.', 'El 90% del impulso ocurrió antes de que abrieran los escáneres principales; volumen vendedor masivo posterior.', 'Aparición de vela de rechazo superior extrema (topping tail); el precio colapsó.');

    -- 3. Emisora 2: APUS ($0.00 PnL)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_TRADE_DISCIPLINE', 'APUS', 0.00, 0, 'Small Cap Momentum', 4200000, 100.0,
        0.00, 0.00, 'Subió de $3.40 a $7.00 respaldada por noticia de 3:40 AM. Aunque formó hombro-cabeza-hombro invertido, marcó continuas mechas de rechazo y falsas rupturas en resistencia sin riesgo claro. Descartada por riesgo no definible.'
    ) RETURNING id INTO v_trade_apus_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_apus_id, 1, 'FILTERING', 6.40, 'Impulso hacia $6.40 y $7.00 con noticia a las 3:40 AM; patrón HCH invertido en gráfico de 5m.', 'Evaluar punto de entrada en resistencia.', 'Múltiples mechas superiores de rechazo y amagos de falso breakout.', 'Imposibilidad de colocar un stop loss con buena relación riesgo/beneficio. Se descartó la compra.');

    -- 4. Emisora 3: MI ($0.00 PnL)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_TRADE_DISCIPLINE', 'MI', 0.00, 0, 'Micro Cap Volatility', 1800000, 220.0,
        0.00, 0.00, 'Disparo vertical de $1.25 a $4.00 en una sola vela de 1 minuto sin noticias. Entró de inmediato en suspensiones por volatilidad (volatility halts), imposibilitando la gestión del riesgo.'
    ) RETURNING id INTO v_trade_mi_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_mi_id, 1, 'FILTERING', 4.00, 'Aparición súbita en el escáner saltando de $1.25 a $4.00 en 60 segundos sin catalizador fundamental.', 'Monitorear Level 2 sin colocar orden.', 'Entrada en múltiples paradas por volatilidad (halts) que congelan la orden y exponen a gaps bajistas.', 'Descartada totalmente; durante un halt el stop loss no se ejecuta y el riesgo es incontrolable.');

END $$;

-- <<< FIN: backend/migration_039_warrior_no_trade_discipline_kb.sql <<<

-- >>> ARCHIVO: backend/migration_040_warrior_wild_card_friday_amod_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 040: SEED DATA CASO "WILD CARD FRIDAY SHORT SQUEEZE (+300% AMOD)" (+$700.00 USD)
-- PATRÓN BANDERA 5M SOBRE 9 EMA (AMOD) Y FILTRO CURL HACIA DOBLE TECHO (TN)
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_5M_BULL_FLAG_9EMA',
    'Bandera Alcista de 5 Minutos sobre 9 EMA (AMOD Pattern)',
    'Patrón de scalping de alta probabilidad en corredores de alto volumen (+200-300%). Requiere MACD positivo; se entra en la bandera de consolidación de 5 minutos apoyada en la media móvil exponencial de 9 períodos (9 EMA) buscando el quiebre hacia número redondo ($4.00) con toma de beneficios inmediata.',
    '08:45-10:15 AM (Pre-Market y Apertura)',
    15000000,
    '{1.50, 8.00}',
    '{"min_volume": 20000000, "surge_min_pct": 100, "require_positive_macd": true}',
    '{"type": "5m_bull_flag_9ema", "target_round_number": true}',
    '{"type": "fast_scalp_whole_number", "target_cents": 0.10, "trailing_stop": false}',
    ARRAY['Buying when MACD is negative', 'Buying curls into double tops in cold tape', 'Holding past whole numbers instead of taking quick scalp']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_tn_id UUID;
    v_trade_amod_id UUID;
BEGIN
    -- 1. Insertar Sesión Wild Card Friday
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-10-18',
        'Wild Card Friday Short Squeeze (+300% AMOD) - (+$700.00)',
        'https://www.youtube.com/watch?v=warrior_wild_card_friday_amod',
        700.00,
        'main_account',
        -18000.00,
        'Sesión de pre-mercado y apertura de un viernes (''Wild Card Friday''), cerrando una semana difícil/roja en un mercado frío. Prioridad: disciplina y protección de capital.',
        'Gestión de tamaño a un décimo (1/10): Debido a la baja liquidez y alta tasa de rechazos, reducir el lote al 10% del estándar blinda el capital. En AMOD descartó compras iniciales por MACD negativo y esperó pacientemente la bandera de 5 minutos sobre la 9 EMA hacia los $4.00. Terminar en verde (+ $700) compensando una pérdida previa cierra la semana en positivo.',
        'Cerró el viernes con ganancia neta verde tras compensar la pérdida de TN (-$1,179.48) con la ganancia de AMOD (+$1,800.00). Mantuvo la disciplina de no sobreoperar en viernes frío.',
        'Sesión Wild Card Friday: AMOD (+300%, +$1,800.00), TN (-$1,179.48). Tamaño de posición al 1/10 (10%).'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: TN (-$1,179.48 USD)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'TN', -1179.48, 150, 'Penny Stocks / Nano Cap', 3500000, 15.0,
        0.61, 0.49, 'Comprar patrón curl hacia doble techo en $0.61 solo subió a $0.70 antes de sufrir un rechazo violento. Salida defensiva perdiendo 11 centavos por acción (-$1,179.48).'
    ) RETURNING id INTO v_trade_tn_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_tn_id, 1, 'ENTRY', 0.61, 'Intento de curvatura alcista (curl) hacia la zona de doble techo.', 'Comprar 10,000 acciones a $0.61.', 'Resistencia pesada en doble techo y mercado frío sin seguimiento.', 'El precio avanzó apenas a $0.70 y fue rechazado con violencia.'),
    (v_trade_tn_id, 2, 'EXIT', 0.49, 'Pérdida rápida de soporte con volumen vendedor.', 'Ejecutar stop loss vendiendo en la caída.', 'Colapso a mínimos si se aguanta la posición.', 'Pérdida de -$1,179.48 USD asumida con disciplina.');

    -- 3. Operación 2: AMOD (+$1,800.00 USD)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_5M_BULL_FLAG_9EMA', 'AMOD', 1800.00, 120, 'Tecnología / Short Squeeze (+300%)', 4500000, 300.0,
        3.90, 4.00, 'Disparo de +300% con más de 100M de volumen. Descartó compras con MACD negativo. Esperó bandera alcista de 5m sobre la 9 EMA y ejecutó scalping rápido hacia la cifra redonda de $4.00 asegurando +$1,800 USD en segundos.'
    ) RETURNING id INTO v_trade_amod_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_amod_id, 1, 'FILTERING', 3.20, 'Impulso temprano con lecturas de MACD negativo / divergencia.', 'Descartar compras iniciales hasta que el indicador confirme alineación.', 'Falso breakout con momentum negativo.', 'Evitó quedar atrapado en el retroceso inicial.'),
    (v_trade_amod_id, 2, 'ENTRY', 3.90, 'Bandera alcista de 5 minutos consolidando sobre la 9 EMA preparándose para quebrar $4.00.', 'Entrar con scalping rápido de 20,000 acciones en la ruptura.', 'Rechazo en número entero psicológico.', 'Aceleración inmediata directa a $4.00.'),
    (v_trade_amod_id, 3, 'EXIT', 4.00, 'Toque del precio en la cifra redonda de $4.00.', 'Venta relámpago de las 20,000 acciones para capturar 10 centavos por acción.', 'Pausa por volatilidad o rechazo en $4.00.', '+$1,800 USD asegurados en segundos; jornada cerrada en verde.');

END $$;

-- <<< FIN: backend/migration_040_warrior_wild_card_friday_amod_kb.sql <<<

-- >>> ARCHIVO: backend/migration_041_scanner_velocity.sql >>>
-- =========================================================================
-- MIGRACIÓN 041: RANKING POR VELOCIDAD (Velocity Score) + GATE DEL PLAYBOOK
-- Claves en stocks_config editables desde Settings / STOCKS
-- =========================================================================
INSERT INTO stocks_config (key, value, description, category, editable, value_type)
VALUES
  ('scanner_min_change_pct',  '3.0',    'Variación mínima del día (%) para aparecer en el escáner de velocidad', 'scanner', true, 'number'),
  ('scanner_min_rvol',        '1.5',    'RVOL mínimo para aparecer en el escáner de velocidad',                  'scanner', true, 'number'),
  ('scanner_min_adx_5m',      '20',     'ADX 5m mínimo (fuerza de tendencia corta)',                             'scanner', true, 'number'),
  ('scanner_min_volume',      '300000', 'Volumen mínimo acumulado del día',                                      'scanner', true, 'number'),
  ('scanner_min_dp5m_pct',    '0.0',    'ΔP mínimo últimos 5 min (%). Bajo este valor + EMA3<EMA9 5m = descendente', 'scanner', true, 'number'),
  ('velocity_w_rvol',         '0.35',   'Peso RVOL en Velocity Score',                                           'scanner', true, 'number'),
  ('velocity_w_adx',          '0.25',   'Peso ADX 5m en Velocity Score',                                         'scanner', true, 'number'),
  ('velocity_w_dp5m',         '0.30',   'Peso ΔP 5m en Velocity Score',                                          'scanner', true, 'number'),
  ('velocity_w_vol',          '0.10',   'Peso Volumen en Velocity Score',                                        'scanner', true, 'number'),
  ('scanner_refresh_seconds', '60',     'Refresco del ranking por velocidad (segundos, mínimo 15)',              'scanner', true, 'number'),
  ('velocity_gate_min_score', '10',     'Velocity Score mínimo vigente al momento del disparo de compra',        'scalping', true, 'number'),
  ('playbook_gate_mode',      'enforce','Gate Playbook Ross Cameron antes de comprar: enforce (bloquea+tamaño) | observe (solo registra)', 'scalping', true, 'select'),
  ('cold_market_spy_pct',     '-0.3',   'Mercado frío si SPY o QQQ varían menos que este % en el día',           'scalping', true, 'number')
ON CONFLICT (key) DO NOTHING;

-- <<< FIN: backend/migration_041_scanner_velocity.sql <<<

-- >>> ARCHIVO: backend/sql/opt_001_foundation.sql >>>
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

-- <<< FIN: backend/sql/opt_001_foundation.sql <<<

-- >>> ARCHIVO: backend/sql/opt_002_universe_data.sql >>>
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

-- <<< FIN: backend/sql/opt_002_universe_data.sql <<<

-- >>> ARCHIVO: backend/sql/opt_003_candidates.sql >>>
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


-- <<< FIN: backend/sql/opt_003_candidates.sql <<<

-- >>> ARCHIVO: backend/sql/opt_004_valuation_aduana.sql >>>
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

-- <<< FIN: backend/sql/opt_004_valuation_aduana.sql <<<

-- >>> ARCHIVO: backend/sql/opt_005_scoring_selector.sql >>>
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


-- <<< FIN: backend/sql/opt_005_scoring_selector.sql <<<

-- >>> ARCHIVO: backend/sql/opt_006_paper_trading_exits.sql >>>
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

-- <<< FIN: backend/sql/opt_006_paper_trading_exits.sql <<<

-- >>> ARCHIVO: backend/sql/opt_007_performance_g3.sql >>>
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

-- <<< FIN: backend/sql/opt_007_performance_g3.sql <<<

-- >>> ARCHIVO: backend/sql/opt_008_retention_cleanup.sql >>>
-- ============================================================
-- eTrader APEX Options - migracion opt_008 (Limpieza y Retención Free Tier)
-- Protege el límite de 500 MB de disco y optimiza Egress en Supabase Free.
-- ============================================================

-- 1. Índices para acelerar el purgado sin bloqueos de tabla
CREATE INDEX IF NOT EXISTS idx_opt_snapshots_captured_at ON opt_snapshots (captured_at);
CREATE INDEX IF NOT EXISTS idx_opt_candidates_status_created ON opt_candidates (eligibility_status, created_at);
CREATE INDEX IF NOT EXISTS idx_opt_aduana_created_at ON opt_aduana_decisions (created_at);

-- 2. Función de mantenimiento para purga periódica
CREATE OR REPLACE FUNCTION cleanup_options_data(
    p_snapshots_days INTEGER DEFAULT 7,
    p_candidates_days INTEGER DEFAULT 3,
    p_jobs_days INTEGER DEFAULT 14
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    deleted_snaps   INTEGER := 0;
    deleted_cands   INTEGER := 0;
    deleted_aduanas INTEGER := 0;
    deleted_jobs    INTEGER := 0;
    result          JSONB;
BEGIN
    -- A. Purgar snapshots antiguos (default: más de 7 días)
    -- Los precios vigentes se conservan intactos en opt_quotes_latest
    DELETE FROM opt_snapshots
    WHERE captured_at < NOW() - (p_snapshots_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_snaps = ROW_COUNT;

    -- B. Purgar candidatas descartadas o expiradas (default: más de 3 días)
    -- NUNCA se eliminan candidatas con estado 'selected' o con trades paper asociados
    DELETE FROM opt_candidates
    WHERE eligibility_status IN ('rejected', 'expired')
      AND created_at < NOW() - (p_candidates_days || ' days')::INTERVAL
      AND NOT EXISTS (
          SELECT 1 FROM opt_paper_trades pt WHERE pt.candidate_id = opt_candidates.id
      );
    GET DIAGNOSTICS deleted_cands = ROW_COUNT;

    -- C. Purgar decisiones ADUANA huérfanas o de candidatas descartadas (> 7 días)
    DELETE FROM opt_aduana_decisions
    WHERE created_at < NOW() - INTERVAL '7 days'
      AND (candidate_id IS NULL OR NOT EXISTS (
          SELECT 1 FROM opt_candidates oc WHERE oc.id = opt_aduana_decisions.candidate_id AND oc.eligibility_status = 'selected'
      ));
    GET DIAGNOSTICS deleted_aduanas = ROW_COUNT;

    -- D. Purgar jobs antiguos completados o con error (> 14 días)
    DELETE FROM opt_jobs
    WHERE status IN ('done', 'error')
      AND created_at < NOW() - (p_jobs_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_jobs = ROW_COUNT;

    result := jsonb_build_object(
        'deleted_snapshots', deleted_snaps,
        'deleted_candidates', deleted_cands,
        'deleted_aduana_decisions', deleted_aduanas,
        'deleted_jobs', deleted_jobs,
        'cleaned_at', NOW()
    );

    RETURN result;
END;
$$;

-- 3. Programación automática con pg_cron (si está habilitado en el proyecto Supabase)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        -- Eliminar schedule previo si existe para evitar duplicación
        BEGIN
            PERFORM cron.unschedule(jobid) FROM cron.job WHERE jobname = 'opt-daily-cleanup';
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
        -- Programar ejecución todos los días a las 03:00 UTC
        PERFORM cron.schedule('opt-daily-cleanup', '0 3 * * *', 'SELECT cleanup_options_data(7, 3, 14);');
    END IF;
EXCEPTION WHEN OTHERS THEN
    -- Si no hay permisos de superusuario para cron, el worker o backend lo ejecuta vía RPC
    NULL;
END;
$$;

-- ROLLBACK:
-- DROP FUNCTION IF EXISTS cleanup_options_data(INTEGER, INTEGER, INTEGER);
-- DROP INDEX IF EXISTS idx_opt_aduana_created_at;
-- DROP INDEX IF EXISTS idx_opt_candidates_status_created;
-- DROP INDEX IF EXISTS idx_opt_snapshots_captured_at;

-- <<< FIN: backend/sql/opt_008_retention_cleanup.sql <<<

-- >>> ARCHIVO: backend/sql/opt_009_catalyst_universe.sql >>>
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

-- <<< FIN: backend/sql/opt_009_catalyst_universe.sql <<<

-- >>> ARCHIVO: backend/sql/opt_010_complementary_architecture.sql >>>
-- ============================================================================
-- Migracion opt_010: Arquitectura Complementaria de Opciones
-- Salud, Control/Kill-Switch, Calendario de Eventos, Desglose de Score (Champion/Challenger),
-- Resultados ADUANA por regla, Libro Contrafactual y Ordenes Paper Multi-pata.
-- ============================================================================

-- 1. Salud del Sistema (Telemetria, p95 quote age, % stale, IBKR connection)
CREATE TABLE IF NOT EXISTS opt_system_health (
    id BIGSERIAL PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'NORMAL',  -- 'NORMAL' | 'DEGRADED' | 'HALTED'
    degraded_reasons JSONB DEFAULT '[]'::jsonb,
    p95_quote_age_sec NUMERIC(8,2) DEFAULT 0.0,
    stale_quotes_pct NUMERIC(5,2) DEFAULT 0.0,
    ibkr_connected BOOLEAN DEFAULT TRUE,
    consecutive_errors INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_sys_health_created ON opt_system_health(created_at DESC);

-- 2. Auditoria de Control y Kill-Switch
CREATE TABLE IF NOT EXISTS opt_control_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,              -- 'mode_change' | 'kill_switch_activated' | 'kill_switch_deactivated' | 'reconciliation_mismatch'
    old_state JSONB DEFAULT '{}'::jsonb,
    new_state JSONB DEFAULT '{}'::jsonb,
    reason TEXT NOT NULL,
    triggered_by VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_control_events_created ON opt_control_events(created_at DESC);

-- 3. Calendario de Eventos Corporativos y Macro (Earnings, Dividendos, Macro FOMC/CPI)
CREATE TABLE IF NOT EXISTS opt_event_calendar (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    event_type VARCHAR(50) NOT NULL,              -- 'earnings' | 'dividend' | 'macro_fomc' | 'split'
    event_time_utc TIMESTAMPTZ,
    source VARCHAR(50) NOT NULL DEFAULT 'hybrid', -- 'stocks_provider' | 'ib_scanner' | 'hybrid'
    verification_state VARCHAR(30) NOT NULL DEFAULT 'CLEAR_VERIFIED', -- 'CLEAR_VERIFIED' | 'EVENT_FOUND' | 'UNKNOWN' | 'STALE'
    details JSONB DEFAULT '{}'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_event_cal_sym_checked ON opt_event_calendar(symbol, checked_at DESC);

-- 4. Puntuaciones y Componentes Desglosados (Champion vs Challenger)
CREATE TABLE IF NOT EXISTS opt_candidate_scores (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT REFERENCES opt_candidates(id) ON DELETE CASCADE,
    score_version VARCHAR(50) NOT NULL,
    model_type VARCHAR(20) NOT NULL DEFAULT 'champion', -- 'champion' | 'challenger'
    score_total NUMERIC(6,2) NOT NULL,
    coverage NUMERIC(5,2) NOT NULL DEFAULT 1.0,
    components JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_components JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_cand_scores_cand_id ON opt_candidate_scores(candidate_id);

-- 5. Resultados de ADUANA por Regla Individual
CREATE TABLE IF NOT EXISTS opt_admission_results (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT REFERENCES opt_candidates(id) ON DELETE CASCADE,
    rule_code VARCHAR(20) NOT NULL,               -- 'O-1'..'O-16'
    passed BOOLEAN NOT NULL,
    status_code VARCHAR(50) NOT NULL DEFAULT 'OK',
    detail TEXT,
    aduana_version VARCHAR(30) NOT NULL DEFAULT 'v2.0-comp',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_adm_res_cand_id ON opt_admission_results(candidate_id);

-- 6. Libro Contrafactual y Analitica Fuera de Muestra
CREATE TABLE IF NOT EXISTS opt_candidate_outcomes (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT REFERENCES opt_candidates(id) ON DELETE CASCADE,
    book VARCHAR(30) NOT NULL DEFAULT 'counterfactual', -- 'selected_paper' | 'shadow' | 'counterfactual'
    symbol VARCHAR(20) NOT NULL,
    strategy_type VARCHAR(50) NOT NULL,
    direction VARCHAR(20) NOT NULL,
    entry_debit NUMERIC(10,4),
    entry_at TIMESTAMPTZ,
    exit_at TIMESTAMPTZ,
    pnl_gross NUMERIC(10,2),
    pnl_net NUMERIC(10,2),
    exit_reason VARCHAR(50),
    reconciled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_cand_outcomes_book ON opt_candidate_outcomes(book, symbol);

-- 7. Columnas adicionales en opt_candidates si no existen
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='ev_robust') THEN
        ALTER TABLE opt_candidates ADD COLUMN ev_robust BOOLEAN DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='ev_range') THEN
        ALTER TABLE opt_candidates ADD COLUMN ev_range JSONB DEFAULT '{}'::jsonb;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='greeks_net') THEN
        ALTER TABLE opt_candidates ADD COLUMN greeks_net JSONB DEFAULT '{}'::jsonb;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='coverage') THEN
        ALTER TABLE opt_candidates ADD COLUMN coverage NUMERIC(5,2) DEFAULT 1.0;
    END IF;
END $$;

-- <<< FIN: backend/sql/opt_010_complementary_architecture.sql <<<



-- Grant schema permissions to PostgREST roles
GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO anon, authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON ROUTINES TO anon, authenticated;
