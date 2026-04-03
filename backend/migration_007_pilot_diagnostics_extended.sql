-- MIGRATION 007 — Extended Pilot Diagnostics & Cache Invalidation
-- Adds performance and specialized logic columns requested for Sprint 1 part 2 validation.

ALTER TABLE pilot_diagnostics 
ADD COLUMN IF NOT EXISTS cycle_type       VARCHAR(5) DEFAULT '15m',
ADD COLUMN IF NOT EXISTS cycle_duration_ms INTEGER,
ADD COLUMN IF NOT EXISTS mtf_score        NUMERIC(6,2),
ADD COLUMN IF NOT EXISTS signal_age_bars  INTEGER,
ADD COLUMN IF NOT EXISTS ai_pattern       TEXT,
ADD COLUMN IF NOT EXISTS ai_agreed        BOOLEAN;

-- Ensure trading_rules table has realtime enabled for cache invalidation
ALTER PUBLICATION supabase_realtime ADD TABLE trading_rules;
