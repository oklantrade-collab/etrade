-- Migration 028: Add math_rationale to fundamental_cache
-- Provides a human-readable explanation of the mathematical valuation.

ALTER TABLE fundamental_cache 
ADD COLUMN IF NOT EXISTS math_rationale TEXT;

COMMENT ON COLUMN fundamental_cache.math_rationale IS 'Explicación detallada de la fórmula y pesos utilizados para el Pro Score matemático';
