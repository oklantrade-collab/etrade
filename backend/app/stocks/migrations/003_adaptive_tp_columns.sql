-- ═══════════════════════════════════════════════════════════════
-- Migration 003: Adaptive TP columns for stocks_positions
-- Date: 2026-04-29
-- ═══════════════════════════════════════════════════════════════

-- PASO 0: Inicializar shares_remaining para posiciones abiertas
UPDATE stocks_positions
SET shares_remaining = shares
WHERE shares_remaining IS NULL
  AND status = 'open';

-- PASO 1: Agregar campos para TP Adaptativo
ALTER TABLE stocks_positions
ADD COLUMN IF NOT EXISTS tp_adaptive_mode    BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS tp_highest_band     INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS tp_rejection_count  INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS tp_rejection_band   INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS tp_exhaustion_score NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS tp_macro_score      NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS tp_adaptive_b1      NUMERIC,
ADD COLUMN IF NOT EXISTS tp_adaptive_b2      NUMERIC,
ADD COLUMN IF NOT EXISTS tp_last_evaluated   TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS tp_exit_signal      VARCHAR(50),
ADD COLUMN IF NOT EXISTS macro_vix           NUMERIC,
ADD COLUMN IF NOT EXISTS macro_spy_change    NUMERIC,
ADD COLUMN IF NOT EXISTS macro_ndx_change    NUMERIC;
