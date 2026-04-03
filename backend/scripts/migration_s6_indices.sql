-- ============================================================
-- eTrader v2 — Sprint 6: Performance Optimization Indices
-- Execute in Supabase SQL Editor
-- ============================================================

-- OPTIMIZATION 1: Ensure critical indices exist for the most
-- frequently queried patterns in the pipeline.

-- Index for candle lookups (most frequent query in the system)
CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf_time
ON market_candles(symbol, timeframe, open_time DESC);

-- Index for indicator lookups
CREATE INDEX IF NOT EXISTS idx_indicators_symbol_tf_time
ON technical_indicators(symbol, timeframe, timestamp DESC);

-- Index for recent signals
CREATE INDEX IF NOT EXISTS idx_signals_created
ON trading_signals(created_at DESC);

-- Index for position status filtering
CREATE INDEX IF NOT EXISTS idx_positions_status
ON positions(status);

-- Index for position symbol + status (for duplicate check)
CREATE INDEX IF NOT EXISTS idx_positions_symbol_status
ON positions(symbol, status);

-- Index for cron_cycles ordering
CREATE INDEX IF NOT EXISTS idx_cron_cycles_started
ON cron_cycles(started_at DESC);

-- Index for system_logs by level and recency
CREATE INDEX IF NOT EXISTS idx_system_logs_level_created
ON system_logs(level, created_at DESC);

-- Index for volume_spikes lookup
CREATE INDEX IF NOT EXISTS idx_volume_spikes_symbol_detected
ON volume_spikes(symbol, detected_at DESC);

-- Index for alert_events
CREATE INDEX IF NOT EXISTS idx_alert_events_sent
ON alert_events(sent_at DESC);

-- ============================================================
-- Verify indices were created
-- ============================================================
SELECT
    indexname,
    tablename,
    pg_size_pretty(pg_relation_size(pg_class.oid)) AS index_size
FROM pg_indexes
JOIN pg_class ON pg_class.relname = pg_indexes.indexname
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
