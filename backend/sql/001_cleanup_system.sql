-- ════════════════════════════════════════════════════════════════
-- eTrade v4 — Sistema de Limpieza Automática de Base de Datos
-- Versión Corregida Final con Jerarquía Orders -> Signals -> Spikes
-- ════════════════════════════════════════════════════════════════

-- ──────────────────────────────────────────
-- PASO 1 — Habilitar pg_cron
-- ──────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- (Jobs legacy se limpian de forma segura en PASO 5)

-- ──────────────────────────────────────────
-- PASO 3 — Tablas de Soporte
-- ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS db_cleanup_log (
  id                  SERIAL PRIMARY KEY,
  executed_at         TIMESTAMPTZ DEFAULT NOW(),
  deleted_candles     INTEGER DEFAULT 0,
  deleted_logs        INTEGER DEFAULT 0,
  deleted_diagnostics INTEGER DEFAULT 0,
  deleted_evaluations INTEGER DEFAULT 0,
  deleted_orders      INTEGER DEFAULT 0,
  deleted_signals     INTEGER DEFAULT 0,
  deleted_spikes      INTEGER DEFAULT 0,
  deleted_indicators  INTEGER DEFAULT 0,
  deleted_regime      INTEGER DEFAULT 0,
  deleted_cron        INTEGER DEFAULT 0,
  deleted_news        INTEGER DEFAULT 0,
  total_deleted       INTEGER DEFAULT 0,
  duration_ms         INTEGER,
  status              VARCHAR(20) DEFAULT 'success',
  error_message       TEXT
);

-- ──────────────────────────────────────────
-- PASO 4 — FUNCIÓN PRINCIPAL DE LIMPIEZA
-- ──────────────────────────────────────────
CREATE OR REPLACE FUNCTION cleanup_database()
RETURNS JSONB
LANGUAGE plpgsql
AS $$
DECLARE
  deleted_candles      INTEGER := 0;
  deleted_logs         INTEGER := 0;
  deleted_diagnostics  INTEGER := 0;
  deleted_evaluations  INTEGER := 0;
  deleted_orders       INTEGER := 0;
  deleted_signals      INTEGER := 0;
  deleted_spikes       INTEGER := 0;
  deleted_indicators   INTEGER := 0;
  deleted_regime       INTEGER := 0;
  deleted_cron         INTEGER := 0;
  deleted_news         INTEGER := 0;
  total_deleted        INTEGER := 0;
  start_time           TIMESTAMPTZ := NOW();
  tmp_count            INTEGER := 0;
  result               JSONB;
BEGIN

  -- ── A. ORDERS & PENDING (Dependen de Signals) ──
  
  -- 1. Pending (7 días)
  DELETE FROM pending_orders
  WHERE status IN ('cancelled','expired','triggered')
    AND created_at < NOW() - INTERVAL '7 days';
  GET DIAGNOSTICS deleted_orders = ROW_COUNT;

  -- 2. Orders Reales (14 días para estados finales)
  DELETE FROM orders
  WHERE status IN ('FILLED', 'CANCELLED', 'EXPIRED', 'REJECTED')
    AND created_at < NOW() - INTERVAL '14 days';
  
  GET DIAGNOSTICS tmp_count = ROW_COUNT;
  deleted_orders := deleted_orders + tmp_count;

  -- ── B. TRADING SIGNALS ──────────────────
  -- Solo borrar señales antiguas que NO tengan órdenes asociadas
  DELETE FROM trading_signals
  WHERE created_at < NOW() - INTERVAL '7 days'
    AND NOT EXISTS (
      SELECT 1 FROM orders o WHERE o.signal_id = trading_signals.id
    );
  GET DIAGNOSTICS deleted_signals = ROW_COUNT;

  -- ── C. VOLUME SPIKES ──────────────────
  -- Solo borrar spikes antiguos que NO tengan señales asociadas
  DELETE FROM volume_spikes
  WHERE detected_at < NOW() - INTERVAL '7 days'
    AND NOT EXISTS (
      SELECT 1 FROM trading_signals ts WHERE ts.spike_id = volume_spikes.id
    );
  GET DIAGNOSTICS deleted_spikes = ROW_COUNT;

  -- ── D. MARKET CANDLES ─────────────────────
  WITH limits AS (
    SELECT * FROM (VALUES
      ('5m',  500),
      ('15m', 300),
      ('30m', 200),
      ('1h',  168),
      ('4h',  180),
      ('1d',  365)
    ) AS t(timeframe, keep_count)
  ),
  ranked AS (
    SELECT mc.id,
      ROW_NUMBER() OVER (
        PARTITION BY mc.symbol, mc.timeframe
        ORDER BY mc.open_time DESC
      ) AS rn,
      l.keep_count
    FROM market_candles mc
    JOIN limits l ON mc.timeframe = l.timeframe
  )
  DELETE FROM market_candles
  WHERE id IN (
    SELECT id FROM ranked WHERE rn > keep_count
  );
  GET DIAGNOSTICS deleted_candles = ROW_COUNT;

  -- ── E. SYSTEM LOGS ────────────────────────
  DELETE FROM system_logs
  WHERE created_at < NOW() - INTERVAL '48 hours';
  GET DIAGNOSTICS deleted_logs = ROW_COUNT;

  -- ── F. PILOT DIAGNOSTICS ─────────────────
  DELETE FROM pilot_diagnostics
  WHERE timestamp < NOW() - INTERVAL '24 hours';
  GET DIAGNOSTICS deleted_diagnostics = ROW_COUNT;

  -- ── G. STRATEGY EVALUATIONS ───────────────
  DELETE FROM strategy_evaluations
  WHERE created_at < NOW() - INTERVAL '7 days';
  GET DIAGNOSTICS deleted_evaluations = ROW_COUNT;

  -- ── H. TECHNICAL INDICATORS ───────────────
  DELETE FROM technical_indicators
  WHERE timestamp < NOW() - INTERVAL '48 hours';
  GET DIAGNOSTICS deleted_indicators = ROW_COUNT;

  -- ── I. MARKET REGIME HISTORY ──────────────
  DELETE FROM market_regime_history
  WHERE evaluated_at < NOW() - INTERVAL '30 days';
  GET DIAGNOSTICS deleted_regime = ROW_COUNT;

  -- ── J. CRON CYCLES ────────────────────────
  DELETE FROM cron_cycles
  WHERE started_at < NOW() - INTERVAL '48 hours';
  GET DIAGNOSTICS deleted_cron = ROW_COUNT;

  -- ── K. NEWS SENTIMENT ─────────────────────
  DELETE FROM news_sentiment
  WHERE analyzed_at < NOW() - INTERVAL '30 days';
  GET DIAGNOSTICS deleted_news = ROW_COUNT;

  -- ── L. TOTAL ──────────────────────────────
  total_deleted := deleted_candles
                 + deleted_logs
                 + deleted_diagnostics
                 + deleted_evaluations
                 + deleted_orders
                 + deleted_signals
                 + deleted_spikes
                 + deleted_indicators
                 + deleted_regime
                 + deleted_cron
                 + deleted_news;

  -- ── M. REGISTRAR EN LOG ───────────────────
  INSERT INTO db_cleanup_log (
    deleted_candles, deleted_logs, deleted_diagnostics,
    deleted_evaluations, deleted_orders, deleted_signals,
    deleted_spikes, deleted_indicators, deleted_regime,
    deleted_cron, deleted_news, total_deleted,
    duration_ms, status
  ) VALUES (
    deleted_candles, deleted_logs, deleted_diagnostics,
    deleted_evaluations, deleted_orders, deleted_signals,
    deleted_spikes, deleted_indicators, deleted_regime,
    deleted_cron, deleted_news, total_deleted,
    EXTRACT(MILLISECONDS FROM (NOW() - start_time))::INTEGER,
    'success'
  );

  -- ── N. LOG EN SYSTEM_LOGS ─────────────────
  INSERT INTO system_logs (module, level, message, created_at)
  VALUES (
    'DB_CLEANUP',
    'INFO',
    format(
      'OK: candles=%s logs=%s diag=%s evals=%s orders=%s signals=%s TOTAL=%s',
      deleted_candles, deleted_logs, deleted_diagnostics,
      deleted_evaluations, deleted_orders, deleted_signals,
      total_deleted
    ),
    NOW()
  );

  result := jsonb_build_object(
    'status',               'success',
    'timestamp',            NOW(),
    'deleted_candles',      deleted_candles,
    'deleted_logs',         deleted_logs,
    'deleted_diagnostics',  deleted_diagnostics,
    'deleted_evaluations',  deleted_evaluations,
    'deleted_orders',       deleted_orders,
    'deleted_signals',      deleted_signals,
    'deleted_spikes',       deleted_spikes,
    'deleted_indicators',   deleted_indicators,
    'deleted_regime',       deleted_regime,
    'deleted_cron',         deleted_cron,
    'deleted_news',         deleted_news,
    'total_deleted',        total_deleted
  );

  RETURN result;

EXCEPTION WHEN OTHERS THEN
  INSERT INTO db_cleanup_log (total_deleted, status, error_message)
  VALUES (0, 'error', SQLERRM);

  INSERT INTO system_logs (module, level, message, created_at)
  VALUES ('DB_CLEANUP', 'ERROR', 'ERROR: ' || SQLERRM, NOW());

  RETURN jsonb_build_object(
    'status',  'error',
    'message', SQLERRM
  );
END;
$$;

-- ──────────────────────────────────────────
-- PASO 5 — Programar con pg_cron
-- ──────────────────────────────────────────

-- Eliminar jobs legados si existen para evitar conflictos
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'hebdomadal-cleanup') THEN
        PERFORM cron.unschedule('hebdomadal-cleanup');
    END IF;
    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'weekly-candle-cleanup') THEN
        PERFORM cron.unschedule('weekly-candle-cleanup');
    END IF;
    -- También desalojar el daily-cleanup anterior para re-insertarlo limpio si se desea
    IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'daily-cleanup') THEN
        PERFORM cron.unschedule('daily-cleanup');
    END IF;
END $$;

-- Programar el nuevo job v4
SELECT cron.schedule(
  'daily-cleanup',
  '0 3 * * *',
  $$SELECT cleanup_database()$$
);

-- ──────────────────────────────────────────
-- PASO 6 — Función de monitoreo (Corregida)
-- ──────────────────────────────────────────
CREATE OR REPLACE FUNCTION get_db_size_report()
RETURNS TABLE (
  tabla           TEXT,
  filas           BIGINT,
  tamanio         TEXT,
  tamanio_bytes   BIGINT
)
LANGUAGE sql
AS $$
  SELECT
    c.relname::TEXT            AS tabla,
    s.n_live_tup::BIGINT       AS filas,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS tamanio,
    pg_total_relation_size(c.oid)::BIGINT AS tamanio_bytes
  FROM pg_class c
  JOIN pg_stat_user_tables s ON c.relname = s.relname
  WHERE c.relkind = 'r' AND c.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
  ORDER BY pg_total_relation_size(c.oid) DESC;
$$;
