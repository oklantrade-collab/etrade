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
