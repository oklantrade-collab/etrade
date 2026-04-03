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
ALTER PUBLICATION supabase_realtime ADD TABLE trading_signals;
ALTER PUBLICATION supabase_realtime ADD TABLE positions;
ALTER PUBLICATION supabase_realtime ADD TABLE alert_events;
ALTER PUBLICATION supabase_realtime ADD TABLE cron_cycles;

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
