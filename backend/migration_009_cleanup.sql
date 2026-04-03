-- MIGRATION 009 — Data Cleanup for Memory-First Architecture
-- This script purges non-relevant historical data that is no longer needed 
-- under the v4 Memory-First (DB-Last) architecture.

-- 1. Purge OHLCV data (Now HOT data, stored in memory)
TRUNCATE TABLE market_candles;

-- 2. Purge Indicator data (Now calculated in memory)
TRUNCATE TABLE technical_indicators;

-- 3. Purge Volume Spike detections (Volatile analysis)
TRUNCATE TABLE volume_spikes CASCADE;

-- 4. Purge old diagnostic/pilot logs to start fresh
TRUNCATE TABLE pilot_diagnostics;

-- 5. Purge old signals (keeping only a clean state for the pilot)
TRUNCATE TABLE trading_signals CASCADE;

-- 6. Optional: Reset WARM state if you want a complete fresh start
-- TRUNCATE TABLE bot_state;
-- TRUNCATE TABLE bot_global_state;
