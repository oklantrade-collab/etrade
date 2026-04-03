-- SPRINT 4: Fix Permissions for Trading Signals
-- Enable public read for trading_signals (anon access)
ALTER TABLE trading_signals ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'trading_signals' AND policyname = 'Allow public read access'
    ) THEN
        CREATE POLICY "Allow public read access" ON trading_signals
            FOR SELECT USING (true);
    END IF;
END $$;

-- Also ensure volume_spikes and cron_cycles are readable
ALTER TABLE volume_spikes ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'volume_spikes' AND policyname = 'Allow public read access'
    ) THEN
        CREATE POLICY "Allow public read access" ON volume_spikes
            FOR SELECT USING (true);
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'positions' AND policyname = 'Allow public read access'
    ) THEN
        CREATE POLICY "Allow public read access" ON positions
            FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies 
        WHERE tablename = 'orders' AND policyname = 'Allow public read access'
    ) THEN
        CREATE POLICY "Allow public read access" ON orders
            FOR SELECT USING (true);
    END IF;
END $$;
