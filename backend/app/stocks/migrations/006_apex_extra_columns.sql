-- APEX Score v1.0 — Migration 006 (Columns for snapshot and technical_scores)

-- Add APEX columns to market_snapshot
ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS apex_4h NUMERIC;
ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS apex_1d NUMERIC;
ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS apex_signal TEXT;
ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS apex_conf TEXT;

-- Add APEX columns to technical_scores (for direct query and dashboard)
ALTER TABLE technical_scores ADD COLUMN IF NOT EXISTS apex_4h NUMERIC;
ALTER TABLE technical_scores ADD COLUMN IF NOT EXISTS apex_1d NUMERIC;
ALTER TABLE technical_scores ADD COLUMN IF NOT EXISTS apex_signal TEXT;
ALTER TABLE technical_scores ADD COLUMN IF NOT EXISTS apex_conf TEXT;
ALTER TABLE technical_scores ADD COLUMN IF NOT EXISTS apex_edge NUMERIC;
