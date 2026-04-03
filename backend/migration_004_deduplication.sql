-- ═══════════════════════════════════════════════════════
-- eTrader v2 — Migration 004: Deduplication
-- Run this in the Supabase SQL Editor
-- ═══════════════════════════════════════════════════════

-- 1. Reassign signals that point to duplicate spikes to the "main" spike ID
WITH mapping AS (
    SELECT id as duplicate_id,
           first_value(id) OVER (PARTITION BY symbol, detected_at ORDER BY id) as main_id
    FROM volume_spikes
)
UPDATE trading_signals t
SET spike_id = m.main_id
FROM mapping m
WHERE t.spike_id = m.duplicate_id
AND m.duplicate_id <> m.main_id;

-- 2. Now safe to delete duplicate spikes
DELETE FROM volume_spikes a USING (
    SELECT id, 
           row_number() OVER (PARTITION BY symbol, detected_at ORDER BY id) as row_num
    FROM volume_spikes
) b
WHERE a.id = b.id 
AND b.row_num > 1;

-- 3. Add unique constraint
ALTER TABLE volume_spikes ADD CONSTRAINT unique_symbol_detected_at UNIQUE (symbol, detected_at);

-- 3. Optimization for trading_signals (if needed)
-- ALTER TABLE trading_signals ADD CONSTRAINT unique_signal_symbol_time UNIQUE (symbol, created_at);

SELECT 'Migration 004 (Deduplication) completed' as status;
