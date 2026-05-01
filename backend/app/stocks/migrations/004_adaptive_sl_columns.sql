-- ═══════════════════════════════════════════════════════════════
-- Migration 004: Adaptive SL columns for stocks_positions and config
-- Date: 2026-04-30
-- ═══════════════════════════════════════════════════════════════

-- Tabla de configuración de Stocks
INSERT INTO stocks_config (key, value, description, category, editable, value_type)
VALUES
  ('sl_close_threshold', '2.0', 'Pérdida % donde cerrar inmediatamente (ideal)', 'stop_loss', true, 'number'),
  ('sl_wait_threshold', '5.0', 'Pérdida % máxima antes de modo espera', 'stop_loss', true, 'number'),
  ('sl_max_wait_days', '5', 'Días máximos esperando recuperación', 'stop_loss', true, 'number'),
  ('sl_support_band', 'lower_2', 'Banda Fibonacci de soporte (lower_1 a lower_6)', 'stop_loss', true, 'select'),
  ('sl_recovery_min_pct', '1.0', 'Recuperación mínima % para no cerrar', 'stop_loss', true, 'number'),
  ('sl_volume_climax_enabled', 'true', 'Detectar climax de volumen (fondo del mercado)', 'stop_loss', true, 'boolean'),
  ('sl_macro_enabled', 'true', 'Usar VIX/SPY/NDX para decisiones de SL', 'stop_loss', true, 'boolean'),
  ('sl_require_candle_confirmation', 'true', 'Requerir vela de confirmación antes de cerrar', 'stop_loss', true, 'boolean'),
  ('sl_max_loss_hard', '12.0', 'Pérdida % máxima absoluta (cierre forzoso)', 'stop_loss', true, 'number'),
  ('sl_bounce_signals_required', '2', 'Señales de rebote mínimas para NO cerrar', 'stop_loss', true, 'number')
ON CONFLICT (key) DO NOTHING;

-- Agregar campos a stocks_positions
ALTER TABLE stocks_positions
ADD COLUMN IF NOT EXISTS sl_mode           VARCHAR(20) DEFAULT 'monitoring',
ADD COLUMN IF NOT EXISTS sl_loss_pct       NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS sl_support_price  NUMERIC,
ADD COLUMN IF NOT EXISTS sl_bounce_score   NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS sl_waiting_since  TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS sl_waiting_days   INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS sl_lowest_price   NUMERIC,
ADD COLUMN IF NOT EXISTS sl_lowest_loss_pct NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS sl_recovery_from_low NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS sl_close_reason   VARCHAR(100),
ADD COLUMN IF NOT EXISTS sl_last_evaluated TIMESTAMPTZ;
