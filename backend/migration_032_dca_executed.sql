-- Migration: Add dca_executed to positions

ALTER TABLE public.positions 
ADD COLUMN IF NOT EXISTS dca_executed BOOLEAN DEFAULT FALSE;
