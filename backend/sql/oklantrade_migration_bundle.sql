-- =========================================================================
-- ETRADE -> OKLANTRADE SUPABASE CONSOLIDATED MIGRATIONS BUNDLE (CLEAN UTF-8)
-- Proyecto: iriotnsoauqrfsjbqyyp (oklantrade-collab's Org)
-- =========================================================================

-- >>> ARCHIVO: backend/migration_014_signals_log.sql >>>
-- MIGRATION 014: signals_log — Auditoría de señales detectadas (Ejecutadas y Bloqueadas)
-- eTrade v4 | Marzo 2026

CREATE TABLE IF NOT EXISTS signals_log (
    id              BIGSERIAL PRIMARY KEY,
    symbol          VARCHAR(30) NOT NULL,
    direction       VARCHAR(10) NOT NULL,
    rule_code       VARCHAR(10),
    price           NUMERIC(20,8),
    score_final     NUMERIC(8,4),
    acted_on        BOOLEAN DEFAULT false,
    reason_skip     TEXT,
    metadata        JSONB,
    detected_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_log_symbol_ts ON signals_log(symbol, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_log_acted_on ON signals_log(acted_on, detected_at DESC);

-- Habilitar tiempo real
ALTER PUBLICATION supabase_realtime ADD TABLE signals_log;

-- <<< FIN: backend/migration_014_signals_log.sql <<<

-- >>> ARCHIVO: backend/migration_033_halcon_centinela.sql >>>
-- ============================================================
-- HALCÓN CENTINELA — Database Migration
-- eTrade v5.0 — Gestor de Cierre Proactivo Multi-Timeframe
-- ============================================================

-- ── 1. Tabla de log de scores HALCÓN ──
-- Registra cada evaluación del motor de scoring por posición
CREATE TABLE IF NOT EXISTS halcon_scores_log (
    id BIGSERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_profile TEXT DEFAULT 'TENDENCIA_SOSTENIDA',
    market_type TEXT DEFAULT 'forex',
    -- Scores por capa (antes de ajustes de régimen)
    score_1d INT DEFAULT 0,
    score_4h INT DEFAULT 0,
    score_15m INT DEFAULT 0,
    score_5m INT DEFAULT 0,
    score_1m INT DEFAULT 0,
    -- Ajustes RSI por capa
    rsi_adj_1d INT DEFAULT 0,
    rsi_adj_4h INT DEFAULT 0,
    rsi_adj_15m INT DEFAULT 0,
    rsi_adj_5m INT DEFAULT 0,
    -- Régimen y compresión
    regime TEXT,
    regime_adx FLOAT,
    compression_index FLOAT,
    compression_timeframe TEXT,
    fib_zone INT,
    fib_multiplier FLOAT DEFAULT 1.0,
    -- Resultado final
    score_final FLOAT NOT NULL,
    semaforo TEXT NOT NULL,
    decision TEXT NOT NULL,
    squeeze_active BOOLEAN DEFAULT FALSE,
    volume_confirmed BOOLEAN,
    -- Ejecución
    executed BOOLEAN DEFAULT FALSE,
    pnl_at_evaluation FLOAT,
    -- Detalle completo (JSON)
    detail JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_halcon_scores_position ON halcon_scores_log(position_id);
CREATE INDEX IF NOT EXISTS idx_halcon_scores_symbol ON halcon_scores_log(symbol);
CREATE INDEX IF NOT EXISTS idx_halcon_scores_created ON halcon_scores_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_halcon_scores_decision ON halcon_scores_log(decision);

-- ── 2. Tabla de decisiones CENTINELA ──
-- Registra cada decisión de cierre/mantener con contexto completo
CREATE TABLE IF NOT EXISTS centinela_decisions_log (
    id BIGSERIAL PRIMARY KEY,
    position_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market_type TEXT DEFAULT 'forex',
    decision TEXT NOT NULL,
    reason TEXT,
    score_final FLOAT,
    pnl_at_decision FLOAT,
    entry_profile TEXT,
    -- ORÁCULO
    oraculo_override BOOLEAN DEFAULT FALSE,
    oraculo_event TEXT,
    -- Ejecución
    executed BOOLEAN DEFAULT FALSE,
    execution_result JSONB,
    -- Arbitraje
    blocked_by TEXT,
    closing_in_progress_set BOOLEAN DEFAULT FALSE,
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_centinela_decisions_position ON centinela_decisions_log(position_id);
CREATE INDEX IF NOT EXISTS idx_centinela_decisions_symbol ON centinela_decisions_log(symbol);
CREATE INDEX IF NOT EXISTS idx_centinela_decisions_created ON centinela_decisions_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_centinela_decisions_executed ON centinela_decisions_log(executed);

-- ── 3. Cache de eventos económicos para ORÁCULO ──
CREATE TABLE IF NOT EXISTS oraculo_events (
    id BIGSERIAL PRIMARY KEY,
    event_name TEXT NOT NULL,
    country TEXT,
    currency TEXT,
    impact TEXT NOT NULL,
    event_datetime TIMESTAMPTZ NOT NULL,
    is_global BOOLEAN DEFAULT FALSE,
    -- Pausa
    trading_paused_symbols TEXT[],
    pause_start TIMESTAMPTZ,
    pause_end TIMESTAMPTZ,
    -- Estado
    processed BOOLEAN DEFAULT FALSE,
    actions_taken JSONB,
    -- Sync
    source TEXT DEFAULT 'finnhub',
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    -- Evitar duplicados
    UNIQUE(event_name, event_datetime)
);

CREATE INDEX IF NOT EXISTS idx_oraculo_events_datetime ON oraculo_events(event_datetime);
CREATE INDEX IF NOT EXISTS idx_oraculo_events_currency ON oraculo_events(currency);
CREATE INDEX IF NOT EXISTS idx_oraculo_events_processed ON oraculo_events(processed);

-- ── 4. Estado CENTINELA por posición ──
-- Almacena el estado de la máquina de estados de cada posición
CREATE TABLE IF NOT EXISTS centinela_position_state (
    position_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    market_type TEXT DEFAULT 'forex',
    -- Estado CENTINELA
    halcon_state TEXT DEFAULT 'NEUTRAL',
    closing_in_progress BOOLEAN DEFAULT FALSE,
    -- Historial
    last_close_action_at TIMESTAMPTZ,
    last_score_final FLOAT,
    last_semaforo TEXT,
    last_decision TEXT,
    -- Cooldown
    cooldown_until TIMESTAMPTZ,
    -- Perfil
    entry_profile TEXT DEFAULT 'TENDENCIA_SOSTENIDA',
    partial_closed_pct FLOAT DEFAULT 0,
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_centinela_state_symbol ON centinela_position_state(symbol);
CREATE INDEX IF NOT EXISTS idx_centinela_state_closing ON centinela_position_state(closing_in_progress);

-- ── 5. Configuración HALCÓN en system_config ──
-- Inserta parámetros configurables como pares clave-valor
INSERT INTO system_config (key, value)
VALUES 
    ('halcon_enabled', 'true'),
    ('halcon_min_profit_usd', '1.0'),
    ('halcon_partial_close_pct', '0.50'),
    ('halcon_adx_range_threshold', '15'),
    ('halcon_adx_trend_threshold', '30'),
    ('halcon_compression_threshold', '0.15'),
    ('halcon_volume_multiplier', '1.3'),
    ('halcon_volume_lookback', '10'),
    ('halcon_atr_pct_threshold', '0.008'),
    ('halcon_rsi_extreme_low', '20'),
    ('halcon_rsi_extreme_high', '80'),
    ('halcon_rsi_extreme_points', '25'),
    ('halcon_rsi_divergence_points', '35'),
    ('halcon_ema_proximity_pct', '0.15'),
    ('halcon_oraculo_enabled', 'true'),
    ('halcon_oraculo_pre_event_min', '60'),
    ('halcon_oraculo_post_event_min', '60'),
    ('halcon_oraculo_close_pnl_threshold', '-5.0'),
    ('halcon_oraculo_bracket_sl_floor', '-8.0'),
    ('halcon_oraculo_calendar_sync_min', '60')
ON CONFLICT (key) DO NOTHING;

-- ── 6. Retención automática — limpiar logs antiguos (>30 días) ──
-- Puede ejecutarse como cron job o scheduled task
-- DELETE FROM halcon_scores_log WHERE created_at < NOW() - INTERVAL '30 days';
-- DELETE FROM centinela_decisions_log WHERE created_at < NOW() - INTERVAL '30 days';
-- DELETE FROM oraculo_events WHERE event_datetime < NOW() - INTERVAL '7 days';

-- <<< FIN: backend/migration_033_halcon_centinela.sql <<<

-- >>> ARCHIVO: backend/migration_034_rebote_aduana.sql >>>
-- migration_034_rebote_aduana.sql
-- Schema additions for the REBOTE / ADUANA entry-management subsystem.

-- 1. rebote_scores_log — every evaluation by ReboteEngine
CREATE TABLE IF NOT EXISTS rebote_scores_log (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    direction       TEXT NOT NULL,           -- 'long' | 'short'
    score_raw       NUMERIC(8,2),
    score_final     NUMERIC(8,2),
    decision        TEXT NOT NULL DEFAULT 'SKIP',
    regime_adx      TEXT,
    regime_local    TEXT,
    contra_trend    BOOLEAN DEFAULT FALSE,
    contra_trend_confirmed BOOLEAN DEFAULT FALSE,
    volume_confirmed BOOLEAN DEFAULT FALSE,
    fib_zone        INT,
    signals         JSONB,
    detail          JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- indices
CREATE INDEX IF NOT EXISTS idx_rebote_log_symbol ON rebote_scores_log(symbol);
CREATE INDEX IF NOT EXISTS idx_rebote_log_created ON rebote_scores_log(created_at);
CREATE INDEX IF NOT EXISTS idx_rebote_log_decision ON rebote_scores_log(decision);

-- 2. aduana_decisions_log
CREATE TABLE IF NOT EXISTS aduana_decisions_log (
    id              BIGSERIAL PRIMARY KEY,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    order_type      TEXT NOT NULL,
    strategy_source TEXT,
    approved        BOOLEAN NOT NULL,
    rule_triggered  TEXT,
    step            INT,
    reason          TEXT,
    detail          JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_aduana_log_symbol ON aduana_decisions_log(symbol);
CREATE INDEX IF NOT EXISTS idx_aduana_log_created ON aduana_decisions_log(created_at);
CREATE INDEX IF NOT EXISTS idx_aduana_log_approved ON aduana_decisions_log(approved);

-- 3. system_config entries for REBOTE/ADUANA
INSERT INTO system_config (key, value, description) VALUES
    ('rebote_enabled', 'true', 'Enable REBOTE entry engine'),
    ('rebote_score_min_entry', '50', 'Minimum score for first REBOTE entry'),
    ('rebote_score_min_additional', '70', 'Minimum score for additional REBOTE entry'),
    ('rebote_adx_range_multiplier', '1.2', 'ADX range multiplier for REBOTE'),
    ('rebote_adx_trend_multiplier', '0.5', 'ADX strong trend multiplier for REBOTE'),
    ('aduana_enabled', 'true', 'Enable ADUANA order validator'),
    ('aduana_impulse_atr_ratio', '1.8', 'Impulse candle ATR ratio threshold for ADUANA')
ON CONFLICT (key) DO NOTHING;

-- <<< FIN: backend/migration_034_rebote_aduana.sql <<<

-- >>> ARCHIVO: backend/migration_035_radar_cascada.sql >>>
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

-- <<< FIN: backend/migration_035_radar_cascada.sql <<<

-- >>> ARCHIVO: backend/migration_036_warrior_playbook_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 036: ROSS CAMERON PLAYBOOK & TRADING EXPERIENCE KNOWLEDGE BASE
-- =========================================================================

-- 1. Tabla de Sesiones Diarias y Contexto de Mentalidad/Gestión
CREATE TABLE IF NOT EXISTS warrior_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trader_name VARCHAR(64) DEFAULT 'Ross Cameron',
    session_date DATE NOT NULL,
    video_title VARCHAR(255) NOT NULL,
    video_url TEXT,
    net_pnl NUMERIC(12, 2) NOT NULL,
    
    -- Contexto Operativo y Mental
    account_mode VARCHAR(64) DEFAULT 'main_account', -- 'main_account', 'small_account', 'split_focus'
    prior_drawdown NUMERIC(12, 2) DEFAULT 0,         -- Ej: -44000
    mental_state TEXT,                               -- Ej: "Racha negativa previa, recuperar disciplina de foco"
    key_mindset_change TEXT,                         -- Ej: "Enfocar solo cuenta grande para no perder velocidad"
    stop_trading_discipline TEXT,                    -- Ej: "Cerrar sesión tras meta, ignorar CZ +140% para no devolver"
    
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Catálogo de Arquetipos de Patrones (Plantillas para el Robot)
CREATE TABLE IF NOT EXISTS warrior_archetypes (
    code VARCHAR(64) PRIMARY KEY,                   -- Ej: 'ROSS_VWAP_BOUNCE_CLEAN'
    name VARCHAR(128) NOT NULL,
    description TEXT,
    ideal_time_window VARCHAR(64),                  -- '08:30-09:30 AM', '09:30-10:30 AM'
    ideal_float_max NUMERIC(12, 2),                 -- Ej: 10000000 (10M shares)
    ideal_price_range NUMERIC(10, 2)[] DEFAULT '{1.50, 15.00}',
    scanner_criteria JSONB NOT NULL,                -- {"min_gap_pct": 20, "min_rvol": 3.0, "running_up": true}
    entry_trigger JSONB NOT NULL,                   -- {"type": "vwap_support", "confirm": "green_candle_rebound"}
    exit_strategy JSONB NOT NULL,                   -- {"type": "scaling_out_into_surges", "max_hold_sec": 180}
    pitfalls_to_avoid TEXT[] DEFAULT '{}',          -- ["200 MA overhead resistance", "High spread dip slippage"]
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Registro de Operaciones Individuales de la Sesión
CREATE TABLE IF NOT EXISTS warrior_trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES warrior_sessions(id) ON DELETE CASCADE,
    archetype_code VARCHAR(64) REFERENCES warrior_archetypes(code),
    ticker VARCHAR(16) NOT NULL,
    pnl NUMERIC(12, 2) NOT NULL,
    duration_seconds INT,                           -- Ej: 120 (2 minutos)
    
    -- Variables del Activo al Momento de Operar
    sector VARCHAR(64),
    float_shares NUMERIC(14, 2),
    premarket_gap_pct NUMERIC(8, 2),
    running_surge_pct NUMERIC(8, 2),
    entry_time TIME,
    exit_time TIME,
    
    -- Métricas de Ejecución
    max_shares_held INT,
    avg_entry_price NUMERIC(10, 4),
    avg_exit_price NUMERIC(10, 4),
    peak_unrealized_pnl NUMERIC(12, 2),
    giveback_pnl NUMERIC(12, 2) DEFAULT 0,
    
    -- Lección Clave del Trade
    key_takeaway TEXT,
    raw_transcript_snippet TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Fases Tácticas Secuenciales del Trade (Paso a Paso de la Decisión)
CREATE TABLE IF NOT EXISTS warrior_trade_phases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id UUID REFERENCES warrior_trades(id) ON DELETE CASCADE,
    sequence_order INT NOT NULL,                    -- 1, 2, 3, 4
    phase_type VARCHAR(32) NOT NULL,                -- 'FILTERING', 'ENTRY', 'SCALING_IN', 'SCALING_OUT', 'DIP_REBUY', 'STOPPED_OUT'
    timestamp_or_time_str VARCHAR(32),              -- Ej: "08:50 AM", "Segundo 45"
    price_level NUMERIC(10, 4),
    shares INT,
    
    -- Lógica del Trader
    trigger_observed TEXT NOT NULL,                 -- Ej: "Precio en $8.00 tocando VWAP tras rechazo de 200 MA"
    action_taken TEXT NOT NULL,                     -- Ej: "Comprar 15,000 acciones buscando rebote limpio"
    risk_factor TEXT,                               -- Ej: "Resistencia de 200 MA overhead en $9.00"
    result_outcome TEXT,                            -- Ej: "Disparo inmediato a $9.50, vender bloque completo"
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Reglas de Inferencia en Tiempo Real para el Robot
CREATE TABLE IF NOT EXISTS warrior_bot_action_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    archetype_code VARCHAR(64) REFERENCES warrior_archetypes(code),
    condition_expression JSONB NOT NULL,
    bot_command VARCHAR(64) NOT NULL,               -- 'BLOCK_FIRST_PULLBACK', 'BUY_VWAP_SUPPORT', 'PYRAMID_SCALE_IN', 'HARD_CUT_SLIPPAGE'
    parameters JSONB NOT NULL,
    priority INT DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE
);

-- =========================================================================
-- SEED DATA: ARQUETIPOS DE PATRONES DE ROSS CAMERON
-- =========================================================================
INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES
(
    'ROSS_VWAP_BOUNCE_CLEAN',
    'Rebote Limpio en Soporte VWAP',
    'Entrada en el primer toque de VWAP tras un impulso inicial fuerte, evitando comprar micro pullbacks si colisionan con resistencias mayores (como la media móvil de 200 periodos).',
    '09:30-10:15 AM',
    20000000,
    '{2.00, 15.00}',
    '{"min_gain_from_open_pct": 30, "min_rvol": 4.0}',
    '{"type": "vwap_touch", "support_buffer_pct": 1.0, "confirm_rebound": true}',
    '{"type": "quick_rip_exit", "target_pct": 15.0, "sell_into_first_red_5s": true}',
    ARRAY['200 MA overhead resistance', 'Falling knife through VWAP without volume bounce']
),
(
    'ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT',
    'Ruptura de Consolidación sobre VWAP',
    'Acción que tuvo un primer empuje, cayó debajo de VWAP, pero logró recuperarse y construir una base plana justo encima de VWAP. Se entra antes del quiebre de números enteros/medios.',
    '08:45-10:30 AM',
    15000000,
    '{1.50, 12.00}',
    '{"min_volume": 1000000, "base_duration_minutes": 5}',
    '{"type": "anticipate_whole_number", "offset_cents": 0.02, "above_vwap": true}',
    '{"type": "scaling_out_into_surges", "tranches": [0.33, 0.33, 0.34]}',
    ARRAY['Dip buying slippage on widening Level 2 spread', 'Breakout fakeout if volume stalls below key level']
),
(
    'ROSS_RUNNING_UP_PYRAMID',
    'Pirámide Acelerada en Escáner Running Up',
    'Acción con catalizador de volumen masivo (+200%) en escáner de alta velocidad. Se entra con lote inicial y se escala agresivamente (scaling in) conforme rompe niveles cada 10-20 centavos.',
    '08:30-09:45 AM',
    8000000,
    '{1.50, 8.00}',
    '{"running_up_scanner": true, "min_gain_pct": 150, "volume_surge_per_min": 500000}',
    '{"type": "pyramid_scaling_in", "initial_tranche_pct": 30, "add_on_breakouts": [0.10, 0.25, 0.50]}',
    '{"type": "parabolic_climax_dump", "exit_on_first_exhaustion_print": true, "max_trade_seconds": 180}',
    ARRAY['Chasing above whole number with exhausted tape', 'Holding through pullbacks on parabolic moves']
)
ON CONFLICT (code) DO NOTHING;

-- =========================================================================
-- SEED DATA: SESIÓN HISTÓRICA +$72,872.42 (JUNIO 2024 / 2026)
-- =========================================================================
DO $$
DECLARE
    v_session_id UUID;
    v_trade_vwave_id UUID;
    v_trade_svre_id UUID;
    v_trade_gem_id UUID;
BEGIN
    -- 1. Insertar Sesión
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-06-28',
        '+$72,872.42 on 3 Explosive Stocks',
        'https://www.youtube.com/watch?v=warrior_trading_72k_recap',
        72872.42,
        'main_account',
        -44000.00,
        'Racha negativa de dos días consecutivos (-$37k y -$22k); foco disperso entre cuentas.',
        'Eliminó la cuenta pequeña de la vista operativa y enfocó el 100% de capital y atención en la cuenta principal para máxima velocidad.',
        'Se detuvo tras el estallido de GEM. Ignoró otros gappers como CZ (+140%) para blindar los $72k ganados.',
        'Cierre de mes récord superando $500,000 en beneficios acumulados.'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: VWave (+$10,000)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_VWAP_BOUNCE_CLEAN', 'VWave', 10000.00, 300, 'Defensa / Aeroespacial', 12000000, 80.0,
        8.00, 9.50, 'Dejar pasar el primer micro-pullback si choca contra la 200 MA. Comprar el rebote limpio en el VWAP.'
    ) RETURNING id INTO v_trade_vwave_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_vwave_id, 1, 'FILTERING', 9.00, 'Precio rozando la media de 200 periodos (200 MA) en $9.00', 'Omitir el primer micro-pullback', '200 MA actúa como techo de resistencia infranqueable en primer intento', 'Evitó quedar atrapado en la trampa'),
    (v_trade_vwave_id, 2, 'ENTRY', 8.00, 'Precio retrocede a $8.00 tocando con precisión la línea del VWAP', 'Comprar soporte VWAP buscando rebote limpio', 'Riesgo de perforación bajista con stop por debajo de $7.80', 'Rebote comprador inmediato con fuerte absorción'),
    (v_trade_vwave_id, 3, 'EXIT', 9.50, 'El precio explota a $9.50 y el Level 2 muestra primer volumen vendedor pesado', 'Vender posición completa', 'Volumen de compradores comenzando a decrecer', 'Asegura +$10,000 limpios y se retira (la acción cayó más tarde)');

    -- 3. Operación 2: SVRE (+$16,000 Netos)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, peak_unrealized_pnl, giveback_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT', 'SVRE', 16000.00, 480, 'Tecnología / Auto', 6500000, 120.0,
        6.98, 8.50, 18800.00, 2800.00, 'Entrada anticipada en $6.98 antes de romper $7.00 sobre VWAP. Alerta: no sobreoperar dips con spread abierto en Level 2.'
    ) RETURNING id INTO v_trade_svre_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_svre_id, 1, 'FILTERING', 8.33, 'Subida inicial a $3.66 luego sube a $8.33 y cae bajo VWAP perdiendo impulso', 'Omitir primeros picos caóticos', 'Acción sobreextendida con riesgo de trampa', 'Esperó consolidación real'),
    (v_trade_svre_id, 2, 'ENTRY', 6.98, 'La acción se monta por encima del VWAP y lateraliza construyendo base', 'Entrar en $6.98 anticipando la ruptura de los $7.00 psicológicos', 'Resistencia psicológica en $7.00', 'Ruptura explosiva con velocidad'),
    (v_trade_svre_id, 3, 'SCALING_OUT', 8.50, 'Precio alcanza tramos de $7.50, $8.00 y $8.50 a $9.00', 'Vender parcialmente en cada impulso', 'Sobreextensión en temporalidad corta', 'Amarra hasta +$18,800 de ganancia no realizada'),
    (v_trade_svre_id, 4, 'DIP_REBUY', 8.00, 'Intento de recompra en retroceso con 10,000 acciones a $8.00', 'Compra en dip', 'Spread amplio en Level 2 provoca slippage al activarse el Stop Loss', 'Devuelve $2,800 a $3,000, cerrando la acción con +$16,000 netos');

    -- 4. Operación 3: GEM (+$46,000 en 2 Minutos)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        max_shares_held, avg_entry_price, avg_exit_price, peak_unrealized_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_RUNNING_UP_PYRAMID', 'GEM', 46000.00, 120, 'Gaming / Entretenimiento', 4200000, 230.0,
        60000, 3.88, 5.58, 48000.00, 'Piramidación agresiva (Scaling In) en acción con aceleración masiva de volumen (>230%). Salida en el clímax parabólico.'
    ) RETURNING id INTO v_trade_gem_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_gem_id, 1, 'FILTERING', 3.57, 'Alerta del escáner "Running Up" a las 8:50 AM cotizando en $3.57 (+230%)', 'Identificar catalizador de volumen extremo', 'Volatilidad salvaje y spreads rápidos', 'Disparo de alerta para entrada inmediata'),
    (v_trade_gem_id, 2, 'ENTRY', 3.70, 'Confirmación de aceleración de cinta Level 2', 'Comprar bloque inicial de 15,000 acciones a $3.70', 'Riesgo de falso breakout', 'La cinta se llena de órdenes verdes a mercado'),
    (v_trade_gem_id, 3, 'SCALING_IN', 3.90, 'El precio vuela y rompe $3.80, $3.95 y $4.00', 'Añadir agresivamente paquetes de 10,000 a 15,000 acciones', 'Aumento de exposición monetaria', 'Construye posición gigante de 45,000 a 60,000 acciones con precio promedio ponderado $3.88'),
    (v_trade_gem_id, 4, 'SCALING_OUT', 4.20, 'Primera aceleración por encima de $4.00', 'Tomar primer beneficio parcial en $4.20', 'Proteger centro de costo', 'Garantiza ganancias base'),
    (v_trade_gem_id, 5, 'SCALING_IN', 5.00, 'Ruptura masiva del nivel entero de $5.00', 'Añade último paquete para la estocada final', 'Riesgo de clímax parabólico inminente', 'Disparo directo hacia $5.50-$5.66'),
    (v_trade_gem_id, 6, 'EXIT', 5.58, 'El precio alcanza $5.58 (el HOD fue $5.66) y aparecen muros de venta en Level 2', 'Vender el bloque principal en el pico', 'Volumen de clímax alcanzado', '+$46,000 asegurados en menos de 120 segundos');

END $$;

-- <<< FIN: backend/migration_036_warrior_playbook_kb.sql <<<

-- >>> ARCHIVO: backend/migration_037_warrior_cold_market_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 037: SEED DATA CASO "DON'T MAKE IT WORSE!" (MERCADO ROJO/FRÍO)
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_COLD_MARKET_DEFENSE',
    'Defensa Activa en Mercado Frío/Rojo (Don''t Make It Worse)',
    'Protocolo de reducción de riesgo y preservación de capital cuando S&P 500 y Nasdaq están en rojo y los breakouts de pequeña capitalización no tienen seguimiento. Tamaño al 25%-33%, prohibidas recompras en techos planos y salida inmediata ante mechas de rechazo.',
    '08:30-09:45 AM',
    10000000,
    '{1.50, 10.00}',
    '{"macro_cold": true, "size_reduction_pct": 70}',
    '{"type": "conservative_dip_only", "require_clean_support": true}',
    '{"type": "quick_rip_scalp", "target_pct": 5.0, "hard_stop_on_topping_tail": true}',
    ARRAY['Overtrading / Revenge trading', 'Buying flat-top squeezes in cold tape', 'Holding through topping tail candles', 'Trading thickly traded or illiquid reverse splits']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_pcla_id UUID;
    v_trade_nwe_id UUID;
    v_trade_davi_id UUID;
BEGIN
    -- 1. Insertar Sesión "Don't Make It Worse!"
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-08-29',
        'Don''t Make It Worse!',
        'https://www.youtube.com/watch?v=warrior_dont_make_it_worse',
        -1516.16,
        'main_account',
        0.00,
        'Mercado frío, lento y errático en pre-mercado con S&P 500 y Nasdaq en rojo; breakouts sin volumen de continuación.',
        'Regla de oro: ''Don''t Make It Worse!''. Reducir el tamaño de posición al 25%-33% del estándar. Aceptar una pérdida pequeña (-$1,500) y proteger el capital en vez de entrar en espiral de venganza arriesgando -$15,000 o -$20,000.',
        'Cerrar la sesión temprano tras detectar mechas de rechazo superiores (topping tails) y giros violentos (jackknife). Dejar de operar antes de que el mercado abra si no hay confirmación.',
        'Sesión defensiva maestra. Operó PCLA (-$1,000), NWE (-$798.16) y DAVI (+$282). Descartó con disciplina NCPL (thickly traded), AXG (sin volumen tras split) y DAIC (noticia positiva pero en cinta roja).'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: PCLA (-$1,000)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'PCLA', -1000.00, 180, 'Salud / Farmacéutica Japonesa', 8000000, 40.0,
        3.20, 3.05, 'En mercado frío, el intento de curl back hacia máximos falló con vela de rechazo superior (topping tail candle). Liquidación defensiva rápida.'
    ) RETURNING id INTO v_trade_pcla_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_pcla_id, 1, 'ENTRY', 3.20, 'Intento de recuperación (curl back) hacia los máximos de la mañana tras rebote inicial.', 'Comprar con tamaño de posición reducido para buscar continuación alcista.', 'Mercado macro frío sin volumen de seguimiento institucional.', 'El precio sube brevemente pero no logra absorber las ventas en la zona alta.'),
    (v_trade_pcla_id, 2, 'EXIT', 3.05, 'Aparición de mecha superior de rechazo (topping tail candle) y reanudación de volumen vendedor.', 'Cortar la posición con pérdida controlada de -$1,000 para no agrandar el daño.', 'Desplome posterior si se intenta aguantar (hope mode).', 'Pérdida pequeña asumida con disciplina; la acción siguió cayendo.');

    -- 3. Operación 2: NWE (-$798.16)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, peak_unrealized_pnl, giveback_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'NWE', -798.16, 360, 'Energía / Utilities', 14000000, 35.0,
        7.25, 7.10, 350.00, 1148.16, 'Ruptura de compresión en techo plano (flat top squeeze) en $7.33 provocó un doble techo y rechazo violento (jackknife). Prohibido forzar recompras en techos en mercado rojo.'
    ) RETURNING id INTO v_trade_nwe_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_nwe_id, 1, 'ENTRY', 6.90, 'Retroceso hacia soporte (buy the dip) tras subida matutina.', 'Comprar en el dip con lote pequeño.', 'Mercado sin momentum.', 'Pequeño rebote aprovechado para tomar una ganancia modesta.'),
    (v_trade_nwe_id, 2, 'ENTRY', 7.25, 'Consolidación en la zona alta buscando compresión alcista (squeeze through flat top) en $7.33.', 'Volver a comprar en la ruptura anticipada.', 'Doble techo en resistencia sin fuerza de ruptura.', 'Fallo rotundo en $7.33 formando doble techo.'),
    (v_trade_nwe_id, 3, 'EXIT', 7.10, 'Rechazo alcista violento en forma de navaja (jackknife reversal) desplomándose en segundos.', 'Venta inmediata para frenar la sangría.', 'Deslizamiento si no se corta en el acto.', 'Devolvió la ganancia inicial y cerró con -$798.16 USD de pérdida neta.');

    -- 4. Operación 3: DAVI (+$282)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, peak_unrealized_pnl, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'DAVI', 282.00, 120, 'Tecnología / Inteligencia Artificial', 7200000, 50.0,
        4.05, 4.15, 350.00, 'En mercado frío, si una ruptura ($4.00) no tiene aceleración inmediata, tomar ganancias mínimas (+3% a +5%) y salir rápido.'
    ) RETURNING id INTO v_trade_davi_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_davi_id, 1, 'ENTRY', 4.05, 'Noticia positiva y gráfico diario similar al patrón de la acción AI, rompiendo los $4.00 buscando $5.00-$6.00.', 'Entrar con lote moderado en la rotura de $4.00.', 'Mercado general apagado que frena los seguimientos.', 'Pequeño empuje comprador hacia $4.15-$4.20.'),
    (v_trade_davi_id, 2, 'EXIT', 4.15, 'Falta de volumen y desaceleración inmediata de la cinta.', 'Vender para asegurar +$282 USD de ganancia parcial.', 'Reversión a negativo si se espera el target optimista de $5.00.', 'Aseguró pequeña ganancia y evitó quedar atrapado en la posterior caída.');

END $$;

-- <<< FIN: backend/migration_037_warrior_cold_market_kb.sql <<<

-- >>> ARCHIVO: backend/migration_038_warrior_monday_squeeze_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 038: SEED DATA CASO "MONDAY SHORT SQUEEZE +225%" (+$9,671.43 USD)
-- MNDR (+225% No News Squeeze), GIXI (+100% Sympathy Wave), WFFF, MEDS
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_NO_NEWS_PARABOLIC_SQUEEZE',
    'Short Squeeze Parabólico Sin Noticias (MNDR Pattern)',
    'Disparo parabólico vertical (>150%-225%) en pre-mercado sin catalizador fundamental. Entrada en micro pullback anticipando números enteros con Stop corto fijo de 10-15 centavos debido a que el soporte estructural está alejado.',
    '07:30-09:15 AM',
    6000000,
    '{0.80, 5.00}',
    '{"no_news_squeeze": true, "surge_min_pct": 100, "tight_micro_stop": true}',
    '{"type": "micro_pullback_whole_number", "anticipation": true}',
    '{"type": "fast_acceleration_exit", "trailing_stop": true, "exit_on_topping_tail": true}',
    ARRAY['Using distant structural support as stop loss (causes massive loss)', 'Entering before 7:15 AM without volume', 'Chasing topping tails above whole number']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_mndr_id UUID;
    v_trade_gixi_id UUID;
    v_trade_wfff_id UUID;
    v_trade_meds_id UUID;
BEGIN
    -- 1. Insertar Sesión de Lunes
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-10-14',
        'Crazy +225% Short Squeeze on Monday Morning! (+$9,671.43)',
        'https://www.youtube.com/watch?v=warrior_monday_squeeze_mndr',
        9671.43,
        'main_account',
        0.00,
        'Apertura de semana (lunes temprano). Enfoque en capturar el lead gapper que despierte el apetito del mercado.',
        'Dominar el Efecto Ola de Simpatía (Sympathy Wave) y la regla de Stop Corto en soporte lejano: Cuando un short squeeze (MNDR +225%) no tiene noticias, el soporte estructural queda a kilómetros ($1.12 vs $1.70); se DEBE usar un stop mental ceñido de 10 a 15 centavos. El calor generado por el primer corredor activa compras masivas en las siguientes acciones con noticias frescas (GIXI a las 7:32 AM).',
        'Cerró la jornada con 5 operaciones ganadoras de 6 (+9,671.43). La única pérdida fue MEDS (-$1,200) a las 7:00 AM por precipitarse antes de que el mercado tuviera volumen real.',
        'Sesión maestra de lunes: MNDR (+$1,300), GIXI (+$7,289.43), WFFF (+$2,282), MEDS (-$1,200). Monitoreó además CLWT, DCX e YMAT.'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: MNDR (+$1,300)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_NEWS_PARABOLIC_SQUEEZE', 'MNDR', 1300.00, 300, 'Tecnología / Salud Móvil (Singapur)', 3200000, 225.0,
        1.70, 2.35, 'Short Squeeze parabólico sin noticias (+225%). Entrada en micro pullback a $1.70 anticipando quiebre de $2.00 con Stop corto de 10-15 centavos porque el soporte real ($1.12) estaba muy lejos.'
    ) RETURNING id INTO v_trade_mndr_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_mndr_id, 1, 'FILTERING', 1.12, 'Disparo vertical inicial desde $0.92 hasta $1.12 y $1.50 sin noticias fundamentales.', 'Dejar pasar el primer tramo parabólico desordenado.', 'Perseguir precios sin soporte definido.', 'Esperó a que el gráfico marcara el primer retroceso ordenado.'),
    (v_trade_mndr_id, 2, 'ENTRY', 1.70, 'Micro pullback limpio alrededor de $1.70 formando bandera antes de la barrera psicológica de $2.00.', 'Comprar en $1.70 anticipando la ruptura de los $2.00.', 'Soporte técnico real muy abajo ($1.12); ratio R:R inviable si se usa soporte base.', 'Aplicó regla de Stop corto fijo de 10-15 centavos (stop en $1.58-$1.60).'),
    (v_trade_mndr_id, 3, 'SCALING_OUT', 2.25, 'Ruptura de los $2.00 disparando con violencia hacia $2.25 y $2.40.', 'Vender bloques parciales en la aceleración.', 'Volatilidad extrema.', 'Aseguró ganancias iniciales sin riesgo.'),
    (v_trade_mndr_id, 4, 'EXIT', 2.50, 'Precio alcanza pico en $2.57-$2.90 y aparecen velas con mechas superiores (topping tail).', 'Venta total asegurando +$1,300 USD de beneficio conservador.', 'Reversión inmediata de short squeeze sin noticias.', 'Salida perfecta antes de la posterior consolidación pesada.');

    -- 3. Operación 2: GIXI (+$7,289.43)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_NEWS_PARABOLIC_SQUEEZE', 'GIXI', 7289.43, 420, 'Tecnología (Israel)', 4800000, 100.0,
        2.10, 3.40, 'Operación estrella de la sesión. Catalizador de noticia a las 7:32 AM montado sobre la ola de simpatía (Sympathy Wave) que MNDR despertó en el mercado.'
    ) RETURNING id INTO v_trade_gixi_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_gixi_id, 1, 'ENTRY', 2.10, 'Noticia publicada a las 7:32 AM con el mercado caliente por la subida de MNDR.', 'Entrar con alta convicción aprovechando el apetito comprador desatado.', 'Falso breakout de pre-mercado.', 'Explosión del 100% hacia $3.50+ con volumen arrollador.'),
    (v_trade_gixi_id, 2, 'EXIT', 3.40, 'Desaceleración de cinta en $3.50 con absorción institucional.', 'Venta en la cima asegurando más de +$7,000 USD de ganancia.', 'Toma masiva de beneficios de pre-mercado.', 'Trade más lucrativo de la jornada matutina.');

    -- 4. Operación 3: WFFF (+$2,282.00)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_CONSOLIDATION_OVER_VWAP_BREAKOUT', 'WFFF', 2282.00, 240, 'Consumo / Agro (Malasia)', 5100000, 45.0,
        12.50, 13.80, 'Operación de continuidad ingresando en $12.50 y tomando beneficios rápidos en la zona de $13.70-$14.69.'
    ) RETURNING id INTO v_trade_wfff_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_wfff_id, 1, 'ENTRY', 12.50, 'Continuación alcista tras consolidación con volumen ascendente.', 'Entrar en $12.50 buscando impulso hacia $14.00.', 'Precio nominal alto ($12+).', 'Disparo limpio hacia $13.70-$14.69.'),
    (v_trade_wfff_id, 2, 'EXIT', 13.80, 'Llegada a resistencia en $14.00.', 'Tomar ganancias rápidas asegurando +$2,282 USD.', 'Rechazo en números enteros.', 'Ganancia capturada con precisión.');

    -- 5. Operación 4: MEDS (-$1,200.00)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'MEDS', -1200.00, 180, 'Salud / Farmacia', 6000000, 25.0,
        3.40, 3.15, 'Única pérdida del día (-$1,200). Comprar patrón curl a las 7:00 AM es prematuro porque el mercado carece de volumen a esa hora.'
    ) RETURNING id INTO v_trade_meds_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_meds_id, 1, 'ENTRY', 3.40, 'Intento de recuperación (curl) a las 7:00 AM.', 'Comprar anticipando continuidad.', 'Hora excesivamente temprana (7:00 AM) con volumen desértico.', 'Falta total de compradores; el precio se desinfló.'),
    (v_trade_meds_id, 2, 'EXIT', 3.15, 'Ruptura a la baja sin soporte de cinta.', 'Cerrar con stop loss defensivo perdiendo -$1,200.', 'Desplome si no se respeta el stop.', 'Pérdida asumida; evitó un castigo mayor.');

END $$;

-- <<< FIN: backend/migration_038_warrior_monday_squeeze_kb.sql <<<

-- >>> ARCHIVO: backend/migration_039_warrior_no_trade_discipline_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 039: SEED DATA CASO "THREE STOCKS ARE UP OVER 100% RIGHT NOW" ($0.00 USD)
-- PROTOCOLO NO TRADE DAY / PRESERVACIÓN EN DRAWDOWN: SIQ, APUS, MI
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_NO_TRADE_DISCIPLINE',
    'Disciplina de Cero Operaciones (No Trade Day / Sidelines)',
    'Protocolo de preservación absoluta de capital y paciencia en drawdown. Cuando activos de +100% muestran movimientos agotados de madrugada (4 AM), rechazos continuos en resistencia sin riesgo claro o paradas por volatilidad (halts), la decisión correcta es quedarse al margen ($0 USD).',
    'Pre-Market / Toda la sesión',
    10000000,
    '{1.00, 20.00}',
    '{"no_trade_filter": true, "require_definable_risk": true}',
    '{"type": "no_entry_stay_on_sidelines", "require_strict_rr": true}',
    '{"type": "capital_preservation", "target_pct": 0.0}',
    ARRAY['Chasing exhausted 4:00 AM spikes', 'Trading choppy resistance without clear stop', 'Buying single-minute spikes into volatility halts', 'Boredom trading during drawdowns']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_siq_id UUID;
    v_trade_apus_id UUID;
    v_trade_mi_id UUID;
BEGIN
    -- 1. Insertar Sesión No Trade Day
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-10-07',
        'Three Stocks Are Up Over 100% RIGHT NOW (No Trade Day - $0.00)',
        'https://www.youtube.com/watch?v=warrior_three_stocks_100_no_trade',
        0.00,
        'main_account',
        -25000.00,
        'Transmisión desde furgoneta Mercedes Sprinter equipada con Starlink. En periodo de recuperación de pérdidas (drawdown); enfoque estricto en paciencia y no forzar operaciones.',
        'Saber cuándo NO operar (''No Trade Day'') es una habilidad táctica maestra. Si una acción subió a las 4 AM y dejó mechas de rechazo (SIQ), si muestra falsas rupturas sin riesgo definible (APUS), o si explota en 1 vela sin noticias y entra en halts (MI), la decisión correcta es quedarse al margen ($0 USD). Preservar el capital en drawdown es la máxima prioridad.',
        'Cero operaciones ejecutadas (0 trades, $0.00 PnL). A pesar de haber 3 acciones con subidas superiores al 100%, ninguna ofreció una relación riesgo/beneficio ejecutable.',
        'Análisis exhaustivo de 3 corredores de más de 100%: SIQ (+900% SPAC), APUS (+100%), MI (+220% en 1m). Todas descartadas con disciplina quirúrgica.'
    ) RETURNING id INTO v_session_id;

    -- 2. Emisora 1: SIQ ($0.00 PnL)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_TRADE_DISCIPLINE', 'SIQ', 0.00, 0, 'SPAC Merger / Wise Space Holdings', 2500000, 900.0,
        0.00, 0.00, 'Subió de $1.80 a $18.37 a las 4:00 AM tras fusión SPAC. A las 6:45 AM el movimiento ya había ocurrido y dejó una vela con enorme mecha superior (topping tail). Descartada por impulso agotado y salida en pánico.'
    ) RETURNING id INTO v_trade_siq_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_siq_id, 1, 'FILTERING', 18.37, 'Explosión de $1.80-$3.60 a $18.37 a las 4:00 AM con fusión de SPAC del viernes.', 'No perseguir en pre-mercado tardío.', 'El 90% del impulso ocurrió antes de que abrieran los escáneres principales; volumen vendedor masivo posterior.', 'Aparición de vela de rechazo superior extrema (topping tail); el precio colapsó.');

    -- 3. Emisora 2: APUS ($0.00 PnL)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_TRADE_DISCIPLINE', 'APUS', 0.00, 0, 'Small Cap Momentum', 4200000, 100.0,
        0.00, 0.00, 'Subió de $3.40 a $7.00 respaldada por noticia de 3:40 AM. Aunque formó hombro-cabeza-hombro invertido, marcó continuas mechas de rechazo y falsas rupturas en resistencia sin riesgo claro. Descartada por riesgo no definible.'
    ) RETURNING id INTO v_trade_apus_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_apus_id, 1, 'FILTERING', 6.40, 'Impulso hacia $6.40 y $7.00 con noticia a las 3:40 AM; patrón HCH invertido en gráfico de 5m.', 'Evaluar punto de entrada en resistencia.', 'Múltiples mechas superiores de rechazo y amagos de falso breakout.', 'Imposibilidad de colocar un stop loss con buena relación riesgo/beneficio. Se descartó la compra.');

    -- 4. Emisora 3: MI ($0.00 PnL)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_NO_TRADE_DISCIPLINE', 'MI', 0.00, 0, 'Micro Cap Volatility', 1800000, 220.0,
        0.00, 0.00, 'Disparo vertical de $1.25 a $4.00 en una sola vela de 1 minuto sin noticias. Entró de inmediato en suspensiones por volatilidad (volatility halts), imposibilitando la gestión del riesgo.'
    ) RETURNING id INTO v_trade_mi_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_mi_id, 1, 'FILTERING', 4.00, 'Aparición súbita en el escáner saltando de $1.25 a $4.00 en 60 segundos sin catalizador fundamental.', 'Monitorear Level 2 sin colocar orden.', 'Entrada en múltiples paradas por volatilidad (halts) que congelan la orden y exponen a gaps bajistas.', 'Descartada totalmente; durante un halt el stop loss no se ejecuta y el riesgo es incontrolable.');

END $$;

-- <<< FIN: backend/migration_039_warrior_no_trade_discipline_kb.sql <<<

-- >>> ARCHIVO: backend/migration_040_warrior_wild_card_friday_amod_kb.sql >>>
-- =========================================================================
-- MIGRACIÓN 040: SEED DATA CASO "WILD CARD FRIDAY SHORT SQUEEZE (+300% AMOD)" (+$700.00 USD)
-- PATRÓN BANDERA 5M SOBRE 9 EMA (AMOD) Y FILTRO CURL HACIA DOBLE TECHO (TN)
-- =========================================================================

INSERT INTO warrior_archetypes (code, name, description, ideal_time_window, ideal_float_max, ideal_price_range, scanner_criteria, entry_trigger, exit_strategy, pitfalls_to_avoid)
VALUES (
    'ROSS_5M_BULL_FLAG_9EMA',
    'Bandera Alcista de 5 Minutos sobre 9 EMA (AMOD Pattern)',
    'Patrón de scalping de alta probabilidad en corredores de alto volumen (+200-300%). Requiere MACD positivo; se entra en la bandera de consolidación de 5 minutos apoyada en la media móvil exponencial de 9 períodos (9 EMA) buscando el quiebre hacia número redondo ($4.00) con toma de beneficios inmediata.',
    '08:45-10:15 AM (Pre-Market y Apertura)',
    15000000,
    '{1.50, 8.00}',
    '{"min_volume": 20000000, "surge_min_pct": 100, "require_positive_macd": true}',
    '{"type": "5m_bull_flag_9ema", "target_round_number": true}',
    '{"type": "fast_scalp_whole_number", "target_cents": 0.10, "trailing_stop": false}',
    ARRAY['Buying when MACD is negative', 'Buying curls into double tops in cold tape', 'Holding past whole numbers instead of taking quick scalp']
)
ON CONFLICT (code) DO NOTHING;

DO $$
DECLARE
    v_session_id UUID;
    v_trade_tn_id UUID;
    v_trade_amod_id UUID;
BEGIN
    -- 1. Insertar Sesión Wild Card Friday
    INSERT INTO warrior_sessions (
        session_date, video_title, video_url, net_pnl, account_mode, prior_drawdown, mental_state, key_mindset_change, stop_trading_discipline, notes
    ) VALUES (
        '2024-10-18',
        'Wild Card Friday Short Squeeze (+300% AMOD) - (+$700.00)',
        'https://www.youtube.com/watch?v=warrior_wild_card_friday_amod',
        700.00,
        'main_account',
        -18000.00,
        'Sesión de pre-mercado y apertura de un viernes (''Wild Card Friday''), cerrando una semana difícil/roja en un mercado frío. Prioridad: disciplina y protección de capital.',
        'Gestión de tamaño a un décimo (1/10): Debido a la baja liquidez y alta tasa de rechazos, reducir el lote al 10% del estándar blinda el capital. En AMOD descartó compras iniciales por MACD negativo y esperó pacientemente la bandera de 5 minutos sobre la 9 EMA hacia los $4.00. Terminar en verde (+ $700) compensando una pérdida previa cierra la semana en positivo.',
        'Cerró el viernes con ganancia neta verde tras compensar la pérdida de TN (-$1,179.48) con la ganancia de AMOD (+$1,800.00). Mantuvo la disciplina de no sobreoperar en viernes frío.',
        'Sesión Wild Card Friday: AMOD (+300%, +$1,800.00), TN (-$1,179.48). Tamaño de posición al 1/10 (10%).'
    ) RETURNING id INTO v_session_id;

    -- 2. Operación 1: TN (-$1,179.48 USD)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_COLD_MARKET_DEFENSE', 'TN', -1179.48, 150, 'Penny Stocks / Nano Cap', 3500000, 15.0,
        0.61, 0.49, 'Comprar patrón curl hacia doble techo en $0.61 solo subió a $0.70 antes de sufrir un rechazo violento. Salida defensiva perdiendo 11 centavos por acción (-$1,179.48).'
    ) RETURNING id INTO v_trade_tn_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_tn_id, 1, 'ENTRY', 0.61, 'Intento de curvatura alcista (curl) hacia la zona de doble techo.', 'Comprar 10,000 acciones a $0.61.', 'Resistencia pesada en doble techo y mercado frío sin seguimiento.', 'El precio avanzó apenas a $0.70 y fue rechazado con violencia.'),
    (v_trade_tn_id, 2, 'EXIT', 0.49, 'Pérdida rápida de soporte con volumen vendedor.', 'Ejecutar stop loss vendiendo en la caída.', 'Colapso a mínimos si se aguanta la posición.', 'Pérdida de -$1,179.48 USD asumida con disciplina.');

    -- 3. Operación 2: AMOD (+$1,800.00 USD)
    INSERT INTO warrior_trades (
        session_id, archetype_code, ticker, pnl, duration_seconds, sector, float_shares, running_surge_pct,
        avg_entry_price, avg_exit_price, key_takeaway
    ) VALUES (
        v_session_id, 'ROSS_5M_BULL_FLAG_9EMA', 'AMOD', 1800.00, 120, 'Tecnología / Short Squeeze (+300%)', 4500000, 300.0,
        3.90, 4.00, 'Disparo de +300% con más de 100M de volumen. Descartó compras con MACD negativo. Esperó bandera alcista de 5m sobre la 9 EMA y ejecutó scalping rápido hacia la cifra redonda de $4.00 asegurando +$1,800 USD en segundos.'
    ) RETURNING id INTO v_trade_amod_id;

    INSERT INTO warrior_trade_phases (trade_id, sequence_order, phase_type, price_level, trigger_observed, action_taken, risk_factor, result_outcome)
    VALUES
    (v_trade_amod_id, 1, 'FILTERING', 3.20, 'Impulso temprano con lecturas de MACD negativo / divergencia.', 'Descartar compras iniciales hasta que el indicador confirme alineación.', 'Falso breakout con momentum negativo.', 'Evitó quedar atrapado en el retroceso inicial.'),
    (v_trade_amod_id, 2, 'ENTRY', 3.90, 'Bandera alcista de 5 minutos consolidando sobre la 9 EMA preparándose para quebrar $4.00.', 'Entrar con scalping rápido de 20,000 acciones en la ruptura.', 'Rechazo en número entero psicológico.', 'Aceleración inmediata directa a $4.00.'),
    (v_trade_amod_id, 3, 'EXIT', 4.00, 'Toque del precio en la cifra redonda de $4.00.', 'Venta relámpago de las 20,000 acciones para capturar 10 centavos por acción.', 'Pausa por volatilidad o rechazo en $4.00.', '+$1,800 USD asegurados en segundos; jornada cerrada en verde.');

END $$;

-- <<< FIN: backend/migration_040_warrior_wild_card_friday_amod_kb.sql <<<

-- >>> ARCHIVO: backend/migration_041_scanner_velocity.sql >>>
-- =========================================================================
-- MIGRACIÓN 041: RANKING POR VELOCIDAD (Velocity Score) + GATE DEL PLAYBOOK
-- Claves en stocks_config editables desde Settings / STOCKS
-- =========================================================================
INSERT INTO stocks_config (key, value, description, category, editable, value_type)
VALUES
  ('scanner_min_change_pct',  '3.0',    'Variación mínima del día (%) para aparecer en el escáner de velocidad', 'scanner', true, 'number'),
  ('scanner_min_rvol',        '1.5',    'RVOL mínimo para aparecer en el escáner de velocidad',                  'scanner', true, 'number'),
  ('scanner_min_adx_5m',      '20',     'ADX 5m mínimo (fuerza de tendencia corta)',                             'scanner', true, 'number'),
  ('scanner_min_volume',      '300000', 'Volumen mínimo acumulado del día',                                      'scanner', true, 'number'),
  ('scanner_min_dp5m_pct',    '0.0',    'ΔP mínimo últimos 5 min (%). Bajo este valor + EMA3<EMA9 5m = descendente', 'scanner', true, 'number'),
  ('velocity_w_rvol',         '0.35',   'Peso RVOL en Velocity Score',                                           'scanner', true, 'number'),
  ('velocity_w_adx',          '0.25',   'Peso ADX 5m en Velocity Score',                                         'scanner', true, 'number'),
  ('velocity_w_dp5m',         '0.30',   'Peso ΔP 5m en Velocity Score',                                          'scanner', true, 'number'),
  ('velocity_w_vol',          '0.10',   'Peso Volumen en Velocity Score',                                        'scanner', true, 'number'),
  ('scanner_refresh_seconds', '60',     'Refresco del ranking por velocidad (segundos, mínimo 15)',              'scanner', true, 'number'),
  ('velocity_gate_min_score', '10',     'Velocity Score mínimo vigente al momento del disparo de compra',        'scalping', true, 'number'),
  ('playbook_gate_mode',      'enforce','Gate Playbook Ross Cameron antes de comprar: enforce (bloquea+tamaño) | observe (solo registra)', 'scalping', true, 'select'),
  ('cold_market_spy_pct',     '-0.3',   'Mercado frío si SPY o QQQ varían menos que este % en el día',           'scalping', true, 'number')
ON CONFLICT (key) DO NOTHING;

-- <<< FIN: backend/migration_041_scanner_velocity.sql <<<

-- >>> ARCHIVO: backend/sql/opt_001_foundation.sql >>>
-- ============================================================
-- eTrader APEX Options - migracion opt_001 (aditiva y reversible)
-- Rollback: ver bloque al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_settings (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL,
    updated_by  TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS opt_settings_audit (
    id             BIGSERIAL PRIMARY KEY,
    settings_version INT NOT NULL,
    key            TEXT NOT NULL,
    old_value      JSONB,
    new_value      JSONB,
    changed_by     TEXT,
    changed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS opt_jobs (
    id          BIGSERIAL PRIMARY KEY,
    type        TEXT NOT NULL CHECK (type IN ('scan','g1_probe','chain_sync','snapshot')),
    params      JSONB NOT NULL DEFAULT '{}'::jsonb,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','done','error','cancelled')),
    result      JSONB,
    error       TEXT,
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_opt_jobs_status ON opt_jobs (status, created_at);

CREATE TABLE IF NOT EXISTS opt_worker_heartbeat (
    worker      TEXT PRIMARY KEY,
    status      TEXT NOT NULL,
    data_state  TEXT,
    detail      JSONB,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Resultado por sesion del Sprint 0.5 (Gate G1)
CREATE TABLE IF NOT EXISTS opt_g1_sessions (
    id                    BIGSERIAL PRIMARY KEY,
    session_date          DATE NOT NULL,
    symbols_evaluated     INT NOT NULL DEFAULT 0,
    optionable_count      INT NOT NULL DEFAULT 0,
    viable_candidates     INT NOT NULL DEFAULT 0,
    market_data_type      TEXT,
    details               JSONB,
    session_pass          BOOLEAN,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_date)
);

-- RLS: sin politicas = solo service_role (backend). Frontend usa la API.
ALTER TABLE opt_settings          ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_settings_audit    ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_jobs              ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_worker_heartbeat  ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_g1_sessions       ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- DROP TABLE IF EXISTS opt_g1_sessions, opt_worker_heartbeat, opt_jobs, opt_settings_audit, opt_settings;

-- <<< FIN: backend/sql/opt_001_foundation.sql <<<

-- >>> ARCHIVO: backend/sql/opt_002_universe_data.sql >>>
-- ============================================================
-- eTrader APEX Options - migracion opt_002 (Sprint 2: universo, contratos, cotizaciones, snapshots)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_underlyings (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL UNIQUE,
    underlying_conid    BIGINT,
    apex_score          NUMERIC,
    direction           TEXT CHECK (direction IN ('bullish','bearish','neutral')),
    price               NUMERIC,
    optionable          BOOLEAN NOT NULL DEFAULT FALSE,
    optionable_reason   TEXT,
    warnings            JSONB NOT NULL DEFAULT '[]'::jsonb,
    strike_gap_pct      NUMERIC,
    atm_spread_pct      NUMERIC,
    atm_oi              NUMERIC,
    atm_volume          NUMERIC,
    iv_hv_ratio         NUMERIC,
    event_flags         JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_state          TEXT,
    last_chain_sync_at  TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS opt_contracts (
    id              BIGSERIAL PRIMARY KEY,
    conid           BIGINT NOT NULL UNIQUE,
    underlying_id   BIGINT NOT NULL REFERENCES opt_underlyings(id) ON DELETE CASCADE,
    "right"         CHAR(1) NOT NULL CHECK ("right" IN ('C','P')),
    strike          NUMERIC NOT NULL CHECK (strike > 0),
    expiry          DATE NOT NULL,
    multiplier      INT NOT NULL DEFAULT 100 CHECK (multiplier > 0),
    trading_class   TEXT,
    exchange        TEXT,
    currency        TEXT NOT NULL DEFAULT 'USD',
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_contracts_lookup ON opt_contracts (underlying_id, expiry, "right", strike);

CREATE TABLE IF NOT EXISTS opt_quotes_latest (
    contract_id        BIGINT PRIMARY KEY REFERENCES opt_contracts(id) ON DELETE CASCADE,
    bid                NUMERIC,
    ask                NUMERIC,
    last               NUMERIC,
    volume             NUMERIC,
    open_interest      NUMERIC,
    iv                 NUMERIC,
    delta              NUMERIC,
    gamma              NUMERIC,
    theta              NUMERIC,
    vega               NUMERIC,
    underlying_price   NUMERIC,
    market_data_type   TEXT NOT NULL CHECK (market_data_type IN ('LIVE','DELAYED','FROZEN','UNKNOWN','STALE','ERROR')),
    usable             BOOLEAN NOT NULL DEFAULT FALSE,
    unusable_reason    TEXT,
    received_at        TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS opt_snapshots (
    id                 BIGSERIAL PRIMARY KEY,
    contract_id        BIGINT NOT NULL REFERENCES opt_contracts(id) ON DELETE CASCADE,
    captured_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    bid                NUMERIC,
    ask                NUMERIC,
    last               NUMERIC,
    volume             NUMERIC,
    open_interest      NUMERIC,
    iv                 NUMERIC,
    delta              NUMERIC,
    gamma              NUMERIC,
    theta              NUMERIC,
    vega               NUMERIC,
    underlying_price   NUMERIC,
    market_data_type   TEXT NOT NULL,
    data_source        TEXT NOT NULL DEFAULT 'ibkr'
);
CREATE INDEX IF NOT EXISTS idx_opt_snapshots_contract_time ON opt_snapshots (contract_id, captured_at DESC);

ALTER TABLE opt_underlyings   ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_contracts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_quotes_latest ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_snapshots     ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- DROP TABLE IF EXISTS opt_snapshots, opt_quotes_latest, opt_contracts, opt_underlyings;

-- <<< FIN: backend/sql/opt_002_universe_data.sql <<<

-- >>> ARCHIVO: backend/sql/opt_003_candidates.sql >>>
-- ============================================================
-- eTrader APEX Options - migracion opt_003 (Sprint 3: candidatas)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_candidates (
    id                   BIGSERIAL PRIMARY KEY,
    underlying_id        BIGINT NOT NULL REFERENCES opt_underlyings(id) ON DELETE CASCADE,
    strategy_type        TEXT NOT NULL CHECK (strategy_type IN ('long_call','long_put','bull_call_spread','bear_put_spread')),
    direction            TEXT NOT NULL CHECK (direction IN ('bullish','bearish')),
    direction_source     TEXT NOT NULL DEFAULT 'unverified',   -- 'apex' | 'unverified'
    expiry               DATE NOT NULL,
    legs                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    qty                  INT CHECK (qty IS NULL OR qty >= 1),
    entry_debit          NUMERIC,            -- por accion, ejecutable
    mid_debit            NUMERIC,
    max_loss_contract    NUMERIC,            -- USD por contrato, con costes
    max_loss_total       NUMERIC,
    max_profit_contract  NUMERIC,            -- NULL = ilimitado teorico
    breakeven            NUMERIC,
    costs_contract       NUMERIC,
    exec_overcost_pct    NUMERIC,
    exit_plan            JSONB,
    -- Se rellenan en Sprints 4-5 (NULL hasta entonces, nunca 0)
    ev_neutral_net       NUMERIC,
    ev_view_net          NUMERIC,
    pop_neutral          NUMERIC,
    pop_view             NUMERIC,
    alpha_used           NUMERIC,
    score                NUMERIC,
    score_breakdown      JSONB,
    eligibility_status   TEXT NOT NULL DEFAULT 'pending'
                         CHECK (eligibility_status IN ('pending','rejected','eligible','selected','expired')),
    rejection_reasons    JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings             JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_quality         JSONB,
    model_version        TEXT NOT NULL,
    settings_version     INT NOT NULL DEFAULT 0,
    snapshot_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_candidates_created_score ON opt_candidates (created_at DESC, score DESC);
CREATE INDEX IF NOT EXISTS idx_opt_candidates_underlying ON opt_candidates (underlying_id, eligibility_status);

ALTER TABLE opt_candidates ENABLE ROW LEVEL SECURITY;


-- Nuevo tipo de job para el worker
ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check;
ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates'));
-- ROLLBACK:
-- DROP TABLE IF EXISTS opt_candidates;
-- ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check; ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot'));


-- <<< FIN: backend/sql/opt_003_candidates.sql <<<

-- >>> ARCHIVO: backend/sql/opt_004_valuation_aduana.sql >>>
-- ============================================================
-- eTrader APEX Options - migracion opt_004 (Sprint 4: simulaciones y decisiones ADUANA)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_simulations (
    id                      BIGSERIAL PRIMARY KEY,
    candidate_id            BIGINT NOT NULL REFERENCES opt_candidates(id) ON DELETE CASCADE,
    scenario_config         JSONB NOT NULL,      -- horizonte, alpha, k, IV de referencia, supuestos
    scenario_results        JSONB NOT NULL,      -- cuadricula movimiento x IV (normal y adverso)
    cost_assumptions        JSONB NOT NULL,
    pricing_model_version   TEXT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_simulations_candidate ON opt_simulations (candidate_id, created_at DESC);

CREATE TABLE IF NOT EXISTS opt_aduana_decisions (
    id              BIGSERIAL PRIMARY KEY,
    candidate_id    BIGINT REFERENCES opt_candidates(id) ON DELETE SET NULL,
    kind            TEXT NOT NULL CHECK (kind IN ('entry','exit','valuation')),
    approved        BOOLEAN NOT NULL,
    rules           JSONB NOT NULL,
    warnings        JSONB NOT NULL DEFAULT '[]'::jsonb,
    settings_version INT NOT NULL DEFAULT 0,
    model_version   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_aduana_candidate ON opt_aduana_decisions (candidate_id, created_at DESC);

-- Reutiliza opt_candidates: las columnas ev_*, pop_*, alpha_used ya existen (Sprint 3). Aqui solo se agrega:
ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS expected_move NUMERIC;
ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS ev_view_adverse NUMERIC;
ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS ev_ratio NUMERIC;
ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS valuation_warnings JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE opt_simulations      ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_aduana_decisions ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- ALTER TABLE opt_candidates DROP COLUMN IF EXISTS valuation_warnings, DROP COLUMN IF EXISTS ev_ratio,
--   DROP COLUMN IF EXISTS ev_view_adverse, DROP COLUMN IF EXISTS expected_move;
-- DROP TABLE IF EXISTS opt_aduana_decisions, opt_simulations;

-- <<< FIN: backend/sql/opt_004_valuation_aduana.sql <<<

-- >>> ARCHIVO: backend/sql/opt_005_scoring_selector.sql >>>
-- ============================================================
-- eTrader APEX Options - migracion opt_005 (Sprint 5: Scoring y Selector de Cartera)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_selections (
    id                      BIGSERIAL PRIMARY KEY,
    session_date            DATE NOT NULL DEFAULT CURRENT_DATE,
    selected_candidate_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
    selections_detail       JSONB NOT NULL DEFAULT '[]'::jsonb,
    skipped_detail          JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_risk_allocated    NUMERIC NOT NULL DEFAULT 0,
    remaining_budget        NUMERIC NOT NULL DEFAULT 0,
    portfolio_state         JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_version           TEXT NOT NULL,
    settings_version        INT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_selections_session ON opt_selections (session_date DESC, created_at DESC);

ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS rank_global INT;
ALTER TABLE opt_candidates ADD COLUMN IF NOT EXISTS rank_strategy INT;

ALTER TABLE opt_selections ENABLE ROW LEVEL SECURITY;

ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check;
ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates','portfolio_select'));

-- ROLLBACK:
-- ALTER TABLE opt_candidates DROP COLUMN IF EXISTS rank_strategy, DROP COLUMN IF EXISTS rank_global;
-- DROP TABLE IF EXISTS opt_selections;
-- ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check; ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates'));


-- <<< FIN: backend/sql/opt_005_scoring_selector.sql <<<

-- >>> ARCHIVO: backend/sql/opt_006_paper_trading_exits.sql >>>
-- ============================================================
-- eTrader APEX Options - migracion opt_006 (Sprint 6: Paper Trading y Salidas)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_paper_trades (
    id                      BIGSERIAL PRIMARY KEY,
    candidate_id            BIGINT REFERENCES opt_candidates(id) ON DELETE SET NULL,
    underlying_id           BIGINT NOT NULL REFERENCES opt_underlyings(id) ON DELETE CASCADE,
    symbol                  TEXT NOT NULL,
    strategy_type           TEXT NOT NULL CHECK (strategy_type IN ('long_call','long_put','bull_call_spread','bear_put_spread')),
    direction               TEXT NOT NULL CHECK (direction IN ('bullish','bearish')),
    status                  TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','cancelled')),
    qty                     INT NOT NULL DEFAULT 1 CHECK (qty >= 1),
    expiry                  DATE NOT NULL,
    entry_time              TIMESTAMPTZ NOT NULL DEFAULT now(),
    entry_debit             NUMERIC NOT NULL,            -- por accion
    entry_fills             JSONB NOT NULL DEFAULT '[]'::jsonb,
    entry_costs             NUMERIC NOT NULL DEFAULT 0,  -- comisiones totales USD
    entry_total_invested    NUMERIC NOT NULL,            -- debit * 100 * qty + costs
    max_loss_total          NUMERIC NOT NULL,
    max_profit_total        NUMERIC,                     -- NULL = ilimitado
    breakeven               NUMERIC,
    exit_time               TIMESTAMPTZ,
    exit_credit             NUMERIC,
    exit_fills              JSONB NOT NULL DEFAULT '[]'::jsonb,
    exit_costs              NUMERIC NOT NULL DEFAULT 0,
    exit_total_recovered    NUMERIC,
    realized_pnl            NUMERIC,
    unrealized_pnl          NUMERIC NOT NULL DEFAULT 0,
    last_mark_price         NUMERIC,
    last_mark_at            TIMESTAMPTZ,
    exit_reason             TEXT CHECK (exit_reason IS NULL OR exit_reason IN ('take_profit','stop_loss','forced_close_time','signal_invalidation','bad_data_close','manual_simulated')),
    exit_plan               JSONB NOT NULL DEFAULT '{}'::jsonb,
    aduana_decision_id      BIGINT REFERENCES opt_aduana_decisions(id) ON DELETE SET NULL,
    model_version           TEXT NOT NULL,
    settings_version        INT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_paper_trades_status ON opt_paper_trades (status, entry_time DESC);
CREATE INDEX IF NOT EXISTS idx_opt_paper_trades_symbol ON opt_paper_trades (symbol, status);

-- Vista de compatibilidad para opt_positions
CREATE OR REPLACE VIEW opt_positions AS SELECT * FROM opt_paper_trades;

CREATE TABLE IF NOT EXISTS opt_risk_events (
    id                      BIGSERIAL PRIMARY KEY,
    paper_trade_id          BIGINT NOT NULL REFERENCES opt_paper_trades(id) ON DELETE CASCADE,
    event_type              TEXT NOT NULL CHECK (event_type IN ('bad_data','stale_quote','signal_flip','time_warning','stop_approaching','early_close_warning','margin_warning','forced_close')),
    details                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_risk_events_trade ON opt_risk_events (paper_trade_id, created_at DESC);

-- Actualizar constraint de opt_jobs para incluir tareas de salida y paper
ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check;
ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates','portfolio_select','exit_check'));

ALTER TABLE opt_paper_trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE opt_risk_events  ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- DROP TABLE IF EXISTS opt_risk_events CASCADE;
-- DROP VIEW IF EXISTS opt_positions CASCADE;
-- DROP TABLE IF EXISTS opt_paper_trades CASCADE;
-- ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check;
-- ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates','portfolio_select'));

-- <<< FIN: backend/sql/opt_006_paper_trading_exits.sql <<<

-- >>> ARCHIVO: backend/sql/opt_007_performance_g3.sql >>>
-- ============================================================
-- eTrader APEX Options - migracion opt_007 (Sprint 7: Performance y Evaluacion Gate G3)
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS opt_g3_evaluations (
    id                      BIGSERIAL PRIMARY KEY,
    evaluation_date         DATE NOT NULL DEFAULT CURRENT_DATE,
    verdict                 TEXT NOT NULL CHECK (verdict IN ('GO', 'NO-GO', 'PENDING')),
    total_trades            INT NOT NULL DEFAULT 0,
    weeks_in_shadow         NUMERIC NOT NULL DEFAULT 0,
    expectancy_usd          NUMERIC NOT NULL DEFAULT 0,
    win_rate_pct            NUMERIC NOT NULL DEFAULT 0,
    max_drawdown_usd        NUMERIC NOT NULL DEFAULT 0,
    calibration_error_pts   NUMERIC NOT NULL DEFAULT 0,
    criteria                JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_version           TEXT NOT NULL,
    settings_version        INT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_opt_g3_eval_date ON opt_g3_evaluations (evaluation_date DESC, created_at DESC);

ALTER TABLE opt_g3_evaluations ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- DROP TABLE IF EXISTS opt_g3_evaluations;

-- <<< FIN: backend/sql/opt_007_performance_g3.sql <<<

-- >>> ARCHIVO: backend/sql/opt_008_retention_cleanup.sql >>>
-- ============================================================
-- eTrader APEX Options - migracion opt_008 (Limpieza y Retención Free Tier)
-- Protege el límite de 500 MB de disco y optimiza Egress en Supabase Free.
-- ============================================================

-- 1. Índices para acelerar el purgado sin bloqueos de tabla
CREATE INDEX IF NOT EXISTS idx_opt_snapshots_captured_at ON opt_snapshots (captured_at);
CREATE INDEX IF NOT EXISTS idx_opt_candidates_status_created ON opt_candidates (eligibility_status, created_at);
CREATE INDEX IF NOT EXISTS idx_opt_aduana_created_at ON opt_aduana_decisions (created_at);

-- 2. Función de mantenimiento para purga periódica
CREATE OR REPLACE FUNCTION cleanup_options_data(
    p_snapshots_days INTEGER DEFAULT 7,
    p_candidates_days INTEGER DEFAULT 3,
    p_jobs_days INTEGER DEFAULT 14
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    deleted_snaps   INTEGER := 0;
    deleted_cands   INTEGER := 0;
    deleted_aduanas INTEGER := 0;
    deleted_jobs    INTEGER := 0;
    result          JSONB;
BEGIN
    -- A. Purgar snapshots antiguos (default: más de 7 días)
    -- Los precios vigentes se conservan intactos en opt_quotes_latest
    DELETE FROM opt_snapshots
    WHERE captured_at < NOW() - (p_snapshots_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_snaps = ROW_COUNT;

    -- B. Purgar candidatas descartadas o expiradas (default: más de 3 días)
    -- NUNCA se eliminan candidatas con estado 'selected' o con trades paper asociados
    DELETE FROM opt_candidates
    WHERE eligibility_status IN ('rejected', 'expired')
      AND created_at < NOW() - (p_candidates_days || ' days')::INTERVAL
      AND NOT EXISTS (
          SELECT 1 FROM opt_paper_trades pt WHERE pt.candidate_id = opt_candidates.id
      );
    GET DIAGNOSTICS deleted_cands = ROW_COUNT;

    -- C. Purgar decisiones ADUANA huérfanas o de candidatas descartadas (> 7 días)
    DELETE FROM opt_aduana_decisions
    WHERE created_at < NOW() - INTERVAL '7 days'
      AND (candidate_id IS NULL OR NOT EXISTS (
          SELECT 1 FROM opt_candidates oc WHERE oc.id = opt_aduana_decisions.candidate_id AND oc.eligibility_status = 'selected'
      ));
    GET DIAGNOSTICS deleted_aduanas = ROW_COUNT;

    -- D. Purgar jobs antiguos completados o con error (> 14 días)
    DELETE FROM opt_jobs
    WHERE status IN ('done', 'error')
      AND created_at < NOW() - (p_jobs_days || ' days')::INTERVAL;
    GET DIAGNOSTICS deleted_jobs = ROW_COUNT;

    result := jsonb_build_object(
        'deleted_snapshots', deleted_snaps,
        'deleted_candidates', deleted_cands,
        'deleted_aduana_decisions', deleted_aduanas,
        'deleted_jobs', deleted_jobs,
        'cleaned_at', NOW()
    );

    RETURN result;
END;
$$;

-- 3. Programación automática con pg_cron (si está habilitado en el proyecto Supabase)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        -- Eliminar schedule previo si existe para evitar duplicación
        BEGIN
            PERFORM cron.unschedule(jobid) FROM cron.job WHERE jobname = 'opt-daily-cleanup';
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
        -- Programar ejecución todos los días a las 03:00 UTC
        PERFORM cron.schedule('opt-daily-cleanup', '0 3 * * *', 'SELECT cleanup_options_data(7, 3, 14);');
    END IF;
EXCEPTION WHEN OTHERS THEN
    -- Si no hay permisos de superusuario para cron, el worker o backend lo ejecuta vía RPC
    NULL;
END;
$$;

-- ROLLBACK:
-- DROP FUNCTION IF EXISTS cleanup_options_data(INTEGER, INTEGER, INTEGER);
-- DROP INDEX IF EXISTS idx_opt_aduana_created_at;
-- DROP INDEX IF EXISTS idx_opt_candidates_status_created;
-- DROP INDEX IF EXISTS idx_opt_snapshots_captured_at;

-- <<< FIN: backend/sql/opt_008_retention_cleanup.sql <<<

-- >>> ARCHIVO: backend/sql/opt_009_catalyst_universe.sql >>>
-- ============================================================
-- eTrader APEX Options & Universe - migracion opt_009
-- Tablas del Universe Pool, eventos de catalizadores y estado
-- Aditiva y reversible. Rollback al final.
-- ============================================================

CREATE TABLE IF NOT EXISTS universe_pool (
    trade_date          DATE NOT NULL,
    symbol              TEXT NOT NULL,
    source              TEXT NOT NULL,            -- 'ib_gain' | 'ib_lose' | 'ib_gap_up' | 'ib_gap_down' | 'ib_volume' | 'yahoo' | 'seed'
    pool_type           TEXT,
    price               NUMERIC,
    prev_close          NUMERIC,
    open_price          NUMERIC,
    change_pct          NUMERIC,
    gap_pct             NUMERIC,
    avg_volume          BIGINT,
    dollar_volume       NUMERIC,
    market_cap          NUMERIC,
    stocks_eligible     BOOLEAN NOT NULL DEFAULT FALSE,
    options_eligible    BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, symbol)
);
CREATE INDEX IF NOT EXISTS idx_universe_pool_date ON universe_pool (trade_date);
CREATE INDEX IF NOT EXISTS idx_universe_pool_options ON universe_pool (trade_date, options_eligible);

CREATE TABLE IF NOT EXISTS universe_catalyst_events (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    catalyst            TEXT NOT NULL CHECK (catalyst IN ('gap_go','sipv_basis_1h','adx_di_5m','rebote_15m')),
    direction           TEXT NOT NULL CHECK (direction IN ('bullish','bearish')),
    strength            NUMERIC,
    timeframe           TEXT,
    bar_time            TIMESTAMPTZ NOT NULL,
    detected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ NOT NULL,
    data_state          TEXT,
    meta                JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (symbol, catalyst, direction, bar_time)
);
CREATE INDEX IF NOT EXISTS idx_catalyst_events_active ON universe_catalyst_events (symbol, expires_at);

CREATE TABLE IF NOT EXISTS universe_catalyst_state (
    symbol              TEXT PRIMARY KEY,
    direction           TEXT CHECK (direction IN ('bullish','bearish','neutral')),
    catalyst_score      NUMERIC,
    rule_applied        TEXT,
    active_catalysts    TEXT[] NOT NULL DEFAULT '{}',
    components          JSONB NOT NULL DEFAULT '{}'::jsonb,
    reasons             JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Columnas adicionales para opt_underlyings
ALTER TABLE opt_underlyings ADD COLUMN IF NOT EXISTS direction_source     TEXT;
ALTER TABLE opt_underlyings ADD COLUMN IF NOT EXISTS catalyst_score       NUMERIC;
ALTER TABLE opt_underlyings ADD COLUMN IF NOT EXISTS catalyst_meta        JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE opt_underlyings ADD COLUMN IF NOT EXISTS catalyst_updated_at  TIMESTAMPTZ;
ALTER TABLE opt_underlyings ADD COLUMN IF NOT EXISTS optionable_checked_at TIMESTAMPTZ;

-- Ampliar tipos de job en opt_jobs para sincronizacion de catalizadores
ALTER TABLE opt_jobs DROP CONSTRAINT IF EXISTS opt_jobs_type_check;
ALTER TABLE opt_jobs ADD CONSTRAINT opt_jobs_type_check 
    CHECK (type IN ('scan','g1_probe','chain_sync','snapshot','candidates','portfolio_select','catalyst_sync'));

-- RLS
ALTER TABLE universe_pool             ENABLE ROW LEVEL SECURITY;
ALTER TABLE universe_catalyst_events  ENABLE ROW LEVEL SECURITY;
ALTER TABLE universe_catalyst_state   ENABLE ROW LEVEL SECURITY;

-- ROLLBACK:
-- DROP TABLE IF EXISTS universe_catalyst_state, universe_catalyst_events, universe_pool;

-- <<< FIN: backend/sql/opt_009_catalyst_universe.sql <<<

-- >>> ARCHIVO: backend/sql/opt_010_complementary_architecture.sql >>>
-- ============================================================================
-- Migracion opt_010: Arquitectura Complementaria de Opciones
-- Salud, Control/Kill-Switch, Calendario de Eventos, Desglose de Score (Champion/Challenger),
-- Resultados ADUANA por regla, Libro Contrafactual y Ordenes Paper Multi-pata.
-- ============================================================================

-- 1. Salud del Sistema (Telemetria, p95 quote age, % stale, IBKR connection)
CREATE TABLE IF NOT EXISTS opt_system_health (
    id BIGSERIAL PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'NORMAL',  -- 'NORMAL' | 'DEGRADED' | 'HALTED'
    degraded_reasons JSONB DEFAULT '[]'::jsonb,
    p95_quote_age_sec NUMERIC(8,2) DEFAULT 0.0,
    stale_quotes_pct NUMERIC(5,2) DEFAULT 0.0,
    ibkr_connected BOOLEAN DEFAULT TRUE,
    consecutive_errors INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_sys_health_created ON opt_system_health(created_at DESC);

-- 2. Auditoria de Control y Kill-Switch
CREATE TABLE IF NOT EXISTS opt_control_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,              -- 'mode_change' | 'kill_switch_activated' | 'kill_switch_deactivated' | 'reconciliation_mismatch'
    old_state JSONB DEFAULT '{}'::jsonb,
    new_state JSONB DEFAULT '{}'::jsonb,
    reason TEXT NOT NULL,
    triggered_by VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_control_events_created ON opt_control_events(created_at DESC);

-- 3. Calendario de Eventos Corporativos y Macro (Earnings, Dividendos, Macro FOMC/CPI)
CREATE TABLE IF NOT EXISTS opt_event_calendar (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    event_type VARCHAR(50) NOT NULL,              -- 'earnings' | 'dividend' | 'macro_fomc' | 'split'
    event_time_utc TIMESTAMPTZ,
    source VARCHAR(50) NOT NULL DEFAULT 'hybrid', -- 'stocks_provider' | 'ib_scanner' | 'hybrid'
    verification_state VARCHAR(30) NOT NULL DEFAULT 'CLEAR_VERIFIED', -- 'CLEAR_VERIFIED' | 'EVENT_FOUND' | 'UNKNOWN' | 'STALE'
    details JSONB DEFAULT '{}'::jsonb,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_event_cal_sym_checked ON opt_event_calendar(symbol, checked_at DESC);

-- 4. Puntuaciones y Componentes Desglosados (Champion vs Challenger)
CREATE TABLE IF NOT EXISTS opt_candidate_scores (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT REFERENCES opt_candidates(id) ON DELETE CASCADE,
    score_version VARCHAR(50) NOT NULL,
    model_type VARCHAR(20) NOT NULL DEFAULT 'champion', -- 'champion' | 'challenger'
    score_total NUMERIC(6,2) NOT NULL,
    coverage NUMERIC(5,2) NOT NULL DEFAULT 1.0,
    components JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_components JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_cand_scores_cand_id ON opt_candidate_scores(candidate_id);

-- 5. Resultados de ADUANA por Regla Individual
CREATE TABLE IF NOT EXISTS opt_admission_results (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT REFERENCES opt_candidates(id) ON DELETE CASCADE,
    rule_code VARCHAR(20) NOT NULL,               -- 'O-1'..'O-16'
    passed BOOLEAN NOT NULL,
    status_code VARCHAR(50) NOT NULL DEFAULT 'OK',
    detail TEXT,
    aduana_version VARCHAR(30) NOT NULL DEFAULT 'v2.0-comp',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_adm_res_cand_id ON opt_admission_results(candidate_id);

-- 6. Libro Contrafactual y Analitica Fuera de Muestra
CREATE TABLE IF NOT EXISTS opt_candidate_outcomes (
    id BIGSERIAL PRIMARY KEY,
    candidate_id BIGINT REFERENCES opt_candidates(id) ON DELETE CASCADE,
    book VARCHAR(30) NOT NULL DEFAULT 'counterfactual', -- 'selected_paper' | 'shadow' | 'counterfactual'
    symbol VARCHAR(20) NOT NULL,
    strategy_type VARCHAR(50) NOT NULL,
    direction VARCHAR(20) NOT NULL,
    entry_debit NUMERIC(10,4),
    entry_at TIMESTAMPTZ,
    exit_at TIMESTAMPTZ,
    pnl_gross NUMERIC(10,2),
    pnl_net NUMERIC(10,2),
    exit_reason VARCHAR(50),
    reconciled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_opt_cand_outcomes_book ON opt_candidate_outcomes(book, symbol);

-- 7. Columnas adicionales en opt_candidates si no existen
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='ev_robust') THEN
        ALTER TABLE opt_candidates ADD COLUMN ev_robust BOOLEAN DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='ev_range') THEN
        ALTER TABLE opt_candidates ADD COLUMN ev_range JSONB DEFAULT '{}'::jsonb;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='greeks_net') THEN
        ALTER TABLE opt_candidates ADD COLUMN greeks_net JSONB DEFAULT '{}'::jsonb;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='opt_candidates' AND column_name='coverage') THEN
        ALTER TABLE opt_candidates ADD COLUMN coverage NUMERIC(5,2) DEFAULT 1.0;
    END IF;
END $$;

-- <<< FIN: backend/sql/opt_010_complementary_architecture.sql <<<
