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
