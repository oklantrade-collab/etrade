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
ALTER PUBLICATION supabase_realtime ADD TABLE trading_signals;
ALTER PUBLICATION supabase_realtime ADD TABLE volume_spikes;
ALTER PUBLICATION supabase_realtime ADD TABLE news_sentiment;

-- Done!
SELECT 'Migration 003 (Sprint 3) completed successfully' AS status;
