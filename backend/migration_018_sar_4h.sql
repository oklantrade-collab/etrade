-- MIGRATION 018 — Parabolic SAR 4h Filter
-- Adds SAR columns to market_snapshot for macro direction filtering

ALTER TABLE market_snapshot
ADD COLUMN IF NOT EXISTS
  sar_4h         NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS
  sar_trend_4h   SMALLINT DEFAULT 0,
ADD COLUMN IF NOT EXISTS
  sar_phase      VARCHAR(10) DEFAULT 'neutral',
ADD COLUMN IF NOT EXISTS
  sar_phase_changed_at TIMESTAMPTZ;

-- Index for performance on phase queries
CREATE INDEX IF NOT EXISTS idx_market_snapshot_sar_phase ON market_snapshot(sar_phase);

-- Step 2.1 — Add SAR to market_candles for chart visualization
ALTER TABLE market_candles
ADD COLUMN IF NOT EXISTS
  sar         NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS
  sar_trend   SMALLINT;

COMMENT ON COLUMN market_snapshot.sar_phase IS 'sar_phase valores: long, short, neutral';
