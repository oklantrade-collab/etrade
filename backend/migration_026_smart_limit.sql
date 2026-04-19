-- migration_026_smart_limit.sql
ALTER TABLE market_snapshot
ADD COLUMN IF NOT EXISTS
  movement_type       VARCHAR(30),
ADD COLUMN IF NOT EXISTS
  basis_slope_pct     NUMERIC,
ADD COLUMN IF NOT EXISTS
  ema200_slope_pct    NUMERIC,
ADD COLUMN IF NOT EXISTS
  movement_confidence NUMERIC,
ADD COLUMN IF NOT EXISTS
  signal_bias         VARCHAR(20),
ADD COLUMN IF NOT EXISTS
  smart_limit_long    NUMERIC,
ADD COLUMN IF NOT EXISTS
  smart_limit_short   NUMERIC,
ADD COLUMN IF NOT EXISTS
  smart_limit_band_long  VARCHAR(20),
ADD COLUMN IF NOT EXISTS
  smart_limit_band_short VARCHAR(20),
ADD COLUMN IF NOT EXISTS
  movement_description TEXT;

ALTER TABLE pending_orders
ADD COLUMN IF NOT EXISTS movement_type VARCHAR(30),
ADD COLUMN IF NOT EXISTS signal_quality VARCHAR(10),
ADD COLUMN IF NOT EXISTS fib_zone_entry INTEGER;
