-- ═══════════════════════════════════════════════════════════
-- MIGRACIÓN: Take Profit en 3 Bloques para stocks_positions
-- Fecha: 2026-04-29
-- ═══════════════════════════════════════════════════════════

ALTER TABLE stocks_positions
  ADD COLUMN IF NOT EXISTS tp_block1_price      NUMERIC,
  ADD COLUMN IF NOT EXISTS tp_block2_price      NUMERIC,
  ADD COLUMN IF NOT EXISTS tp_block3_price      NUMERIC,
  ADD COLUMN IF NOT EXISTS tp_block1_executed   BOOLEAN DEFAULT false,
  ADD COLUMN IF NOT EXISTS tp_block2_executed   BOOLEAN DEFAULT false,
  ADD COLUMN IF NOT EXISTS tp_block3_executed   BOOLEAN DEFAULT false,
  ADD COLUMN IF NOT EXISTS tp_block1_shares     NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_block2_shares     NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_block3_shares     NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_block1_pnl        NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_block2_pnl        NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_block3_pnl        NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_delta_method      VARCHAR(30),
  ADD COLUMN IF NOT EXISTS tp_delta_value       NUMERIC,
  ADD COLUMN IF NOT EXISTS tp_atr_14            NUMERIC,
  ADD COLUMN IF NOT EXISTS tp_buy_strength      VARCHAR(20),
  ADD COLUMN IF NOT EXISTS tp_trailing_high     NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS tp_trailing_sl       NUMERIC DEFAULT 0,
  ADD COLUMN IF NOT EXISTS shares_remaining     NUMERIC;

-- Verificar columnas creadas:
SELECT column_name
FROM information_schema.columns
WHERE table_name = 'stocks_positions'
  AND column_name LIKE 'tp_%'
ORDER BY column_name;
