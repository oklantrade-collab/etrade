-- Migration 027: Add AI summaries to fundamental_cache
-- Enables persistence of AI rationale in the mathematical valuation engine.

ALTER TABLE fundamental_cache 
ADD COLUMN IF NOT EXISTS qwen_summary TEXT,
ADD COLUMN IF NOT EXISTS gemini_summary TEXT;

COMMENT ON COLUMN fundamental_cache.qwen_summary IS 'Resumen del análisis fundamental realizado por Qwen/OpenAI';
COMMENT ON COLUMN fundamental_cache.gemini_summary IS 'Resumen del análisis fundamental realizado por Google Gemini';
