-- ============================================================================
-- migration_035_radar_cascada.sql
-- RADAR and CASCADA modules integration schema updates
-- ============================================================================

-- 1. Add 'origen' column to forex_positions and positions (if not already present)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'origen'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN origen VARCHAR(50) DEFAULT 'STANDARD';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'origen'
    ) THEN
        ALTER TABLE positions ADD COLUMN origen VARCHAR(50) DEFAULT 'STANDARD';
    END IF;
END $$;

-- 2. Add CASCADA state columns to forex_positions and positions
DO $$
BEGIN
    -- forex_positions
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'cascade_level'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN cascade_level INT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'cascade_hold'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN cascade_hold BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'forex_positions' AND column_name = 'pnl_pico'
    ) THEN
        ALTER TABLE forex_positions ADD COLUMN pnl_pico NUMERIC(12, 4) DEFAULT NULL;
    END IF;

    -- positions (crypto)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'cascade_level'
    ) THEN
        ALTER TABLE positions ADD COLUMN cascade_level INT DEFAULT NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'cascade_hold'
    ) THEN
        ALTER TABLE positions ADD COLUMN cascade_hold BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'positions' AND column_name = 'pnl_pico'
    ) THEN
        ALTER TABLE positions ADD COLUMN pnl_pico NUMERIC(20, 8) DEFAULT NULL;
    END IF;
END $$;

-- 3. Create cascada_decisions_log table
CREATE TABLE IF NOT EXISTS cascada_decisions_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id TEXT NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    market_type VARCHAR(20) DEFAULT 'forex',
    cascade_level INT NOT NULL,
    previous_level INT,
    level_advanced BOOLEAN DEFAULT FALSE,
    check_type VARCHAR(30) NOT NULL, -- 'rebote', 'continuacion', 'giveback', 'hold'
    decision VARCHAR(30) NOT NULL,   -- 'CERRAR', 'MANTENER', 'GIVEBACK_CLOSE', 'HOLD'
    cascade_hold BOOLEAN DEFAULT FALSE,
    pnl_current NUMERIC(12, 4),
    pnl_pico NUMERIC(12, 4),
    giveback_pct NUMERIC(6, 2),
    signals JSONB,
    slope_table JSONB,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cascada_decisions_pos ON cascada_decisions_log(position_id);
CREATE INDEX IF NOT EXISTS idx_cascada_decisions_sym ON cascada_decisions_log(symbol);
CREATE INDEX IF NOT EXISTS idx_cascada_decisions_created ON cascada_decisions_log(created_at);

-- 4. Add system_config entries for RADAR and CASCADA
INSERT INTO system_config (key, value, description) VALUES
    ('radar_enabled', 'true'::jsonb, 'Activar bus de señales compartido RADAR'),
    ('radar_slope_ascending_threshold', '0.15'::jsonb, 'Umbral de pendiente ascendente normalizada ATR'),
    ('radar_slope_descending_threshold', '-0.15'::jsonb, 'Umbral de pendiente descendente normalizada ATR'),
    ('radar_slope_lookback_candles', '3'::jsonb, 'Número de velas cerradas para cálculo de pendiente'),
    ('cascada_enabled', 'true'::jsonb, 'Activar gestor de posiciones CASCADA'),
    ('cascada_giveback_threshold_pct', '0.50'::jsonb, 'Umbral de retroceso de PNL pico para forzar cierre (50%)'),
    ('cascada_support_signal_bb_tf', '"15m"'::jsonb, 'Timeframe para señal de apoyo Bollinger'),
    ('cascada_support_signal_hh_tf_n1', '"15m"'::jsonb, 'Timeframe para señal de apoyo HH descendentes en N1'),
    ('cascada_support_signal_hh_tf_n2_n5', '"1h"'::jsonb, 'Timeframe para señal de apoyo HH descendentes en N2 a N5')
ON CONFLICT (key) DO NOTHING;
