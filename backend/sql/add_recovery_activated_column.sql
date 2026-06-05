-- Migration: Add recovery_activated_at column to all positions tables
-- Run this in your Supabase Dashboard > SQL Editor

ALTER TABLE positions ADD COLUMN IF NOT EXISTS recovery_activated_at TIMESTAMPTZ;
ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS recovery_activated_at TIMESTAMPTZ;
ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS recovery_activated_at TIMESTAMPTZ;

-- Re-enable schema cache reload to update the API endpoints
NOTIFY pgrst, 'reload schema';
