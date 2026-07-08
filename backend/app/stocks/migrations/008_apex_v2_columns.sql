-- ════════════════════════════════════════════
-- APEX Score v2.0 — Database Migration
-- 3 dimensiones: APEX + XG + TIMING
-- ════════════════════════════════════════════

-- Bloque 6 (Growth Acceleration)
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS b6_growth NUMERIC;

-- XG Score (Potencial Explosivo)
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS xg_score NUMERIC;
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS xg_detail JSONB;

-- Timing Score (Momento de Entrada)
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS timing_score NUMERIC;
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS timing_detail JSONB;

-- Trade Score (Output Final Combinado)
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS trade_score NUMERIC;
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS etv NUMERIC;
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS upside_expected NUMERIC;
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS downside_risk NUMERIC;

-- Métricas nuevas de B3
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS peg_ratio NUMERIC;
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS fcf_yield NUMERIC;
ALTER TABLE apex_scores ADD COLUMN IF NOT EXISTS market_cap_tier VARCHAR(10);

-- Índice para Trade Score
CREATE INDEX IF NOT EXISTS idx_apex_trade_score
ON apex_scores(trade_score DESC, calculated_at DESC);

-- market_snapshot — nuevas columnas
ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS trade_score NUMERIC;
ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS xg_score NUMERIC;
ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS timing_score NUMERIC;
ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS etv NUMERIC;

-- fundamental_cache — nuevas columnas de APEX v2.0
ALTER TABLE fundamental_cache ADD COLUMN IF NOT EXISTS peg_ratio NUMERIC;
ALTER TABLE fundamental_cache ADD COLUMN IF NOT EXISTS pe_ratio NUMERIC;
ALTER TABLE fundamental_cache ADD COLUMN IF NOT EXISTS forward_pe NUMERIC;
ALTER TABLE fundamental_cache ADD COLUMN IF NOT EXISTS free_cash_flow NUMERIC;
ALTER TABLE fundamental_cache ADD COLUMN IF NOT EXISTS eps_growth_qoq NUMERIC;
ALTER TABLE fundamental_cache ADD COLUMN IF NOT EXISTS short_percent_float NUMERIC;
ALTER TABLE fundamental_cache ADD COLUMN IF NOT EXISTS revenue_growth_qoq NUMERIC;
ALTER TABLE fundamental_cache ADD COLUMN IF NOT EXISTS fcf_growth_pct NUMERIC;
