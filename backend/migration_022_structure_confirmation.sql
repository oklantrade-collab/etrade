-- Migration 022: Market Structure Confirmation columns
-- Adds structure analysis results for 15m and 4h timeframes

ALTER TABLE market_snapshot
ADD COLUMN IF NOT EXISTS structure_15m        VARCHAR(20) DEFAULT 'unknown',
ADD COLUMN IF NOT EXISTS allow_long_15m       BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS allow_short_15m      BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS reverse_signal_15m   BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS structure_reason_15m TEXT,
ADD COLUMN IF NOT EXISTS structure_4h         VARCHAR(20) DEFAULT 'unknown',
ADD COLUMN IF NOT EXISTS allow_long_4h        BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS allow_short_4h       BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS reverse_signal_4h    BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS structure_reason_4h  TEXT;
