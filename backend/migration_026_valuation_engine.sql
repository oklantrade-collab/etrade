
-- eTrader v4.5 — VALUATION ENGINE Migration
-- Adds columns to fundamental_cache for mathematical valuation storage

ALTER TABLE fundamental_cache
ADD COLUMN IF NOT EXISTS piotroski_score INTEGER,
ADD COLUMN IF NOT EXISTS piotroski_detail JSONB,
ADD COLUMN IF NOT EXISTS graham_number NUMERIC,
ADD COLUMN IF NOT EXISTS graham_margin NUMERIC,
ADD COLUMN IF NOT EXISTS dcf_intrinsic NUMERIC,
ADD COLUMN IF NOT EXISTS dcf_upside_pct NUMERIC,
ADD COLUMN IF NOT EXISTS altman_z_score NUMERIC,
ADD COLUMN IF NOT EXISTS altman_zone VARCHAR(20),
ADD COLUMN IF NOT EXISTS math_score NUMERIC,
ADD COLUMN IF NOT EXISTS ia_score NUMERIC,
ADD COLUMN IF NOT EXISTS data_source VARCHAR(50),
ADD COLUMN IF NOT EXISTS valuation_status VARCHAR(30),
ADD COLUMN IF NOT EXISTS composite_intrinsic NUMERIC;

COMMENT ON COLUMN fundamental_cache.piotroski_score IS 'Piotroski F-Score (0-9)';
COMMENT ON COLUMN fundamental_cache.graham_number IS 'Intrinsic value using Graham Number formula';
COMMENT ON COLUMN fundamental_cache.dcf_intrinsic IS 'Intrinsic value using Discounted Cash Flow';
COMMENT ON COLUMN fundamental_cache.math_score IS 'Composite Pro Score based only on mathematical models (1-10)';
COMMENT ON COLUMN fundamental_cache.ia_score IS 'Pro Score provided by AI (1-10)';
