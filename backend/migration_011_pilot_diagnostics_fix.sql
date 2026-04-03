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
