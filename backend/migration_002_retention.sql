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
