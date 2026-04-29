-- SLVM Migration: Stop Loss Virtual con Modo Recuperacion
-- Run this in Supabase SQL Editor

ALTER TABLE positions ADD COLUMN IF NOT EXISTS slv_price NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS slv_triggered BOOLEAN DEFAULT false;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS slv_triggered_at TIMESTAMPTZ;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS slv_triggered_price NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS recovery_mode BOOLEAN DEFAULT false;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS recovery_cycles INTEGER DEFAULT 0;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS recovery_max_cycles INTEGER DEFAULT 12;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS recovery_target_price NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS recovery_exit_price NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS recovery_exit_reason VARCHAR(50);
ALTER TABLE positions ADD COLUMN IF NOT EXISTS lowest_price_in_recovery NUMERIC;
ALTER TABLE positions ADD COLUMN IF NOT EXISTS recovery_pnl_pips NUMERIC;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS slv_price NUMERIC;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS slv_triggered BOOLEAN DEFAULT false;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS slv_triggered_at TIMESTAMPTZ;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS slv_triggered_price NUMERIC;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS recovery_mode BOOLEAN DEFAULT false;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS recovery_cycles INTEGER DEFAULT 0;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS recovery_max_cycles INTEGER DEFAULT 12;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS recovery_target_price NUMERIC;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS recovery_exit_price NUMERIC;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS recovery_exit_reason VARCHAR(50);
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS lowest_price_in_recovery NUMERIC;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS recovery_pnl_pips NUMERIC;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS slv_price NUMERIC;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS slv_triggered BOOLEAN DEFAULT false;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS slv_triggered_at TIMESTAMPTZ;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS slv_triggered_price NUMERIC;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS recovery_mode BOOLEAN DEFAULT false;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS recovery_cycles INTEGER DEFAULT 0;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS recovery_max_cycles INTEGER DEFAULT 12;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS recovery_target_price NUMERIC;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS recovery_exit_price NUMERIC;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS recovery_exit_reason VARCHAR(50);
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS lowest_price_in_recovery NUMERIC;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS recovery_pnl_pips NUMERIC;

-- Verify:
SELECT column_name FROM information_schema.columns WHERE table_name = 'positions' AND (column_name LIKE '%slv%' OR column_name LIKE '%recovery%') ORDER BY column_name;
SELECT column_name FROM information_schema.columns WHERE table_name = 'forex_positions' AND (column_name LIKE '%slv%' OR column_name LIKE '%recovery%') ORDER BY column_name;
SELECT column_name FROM information_schema.columns WHERE table_name = 'stocks_positions' AND (column_name LIKE '%slv%' OR column_name LIKE '%recovery%') ORDER BY column_name;
