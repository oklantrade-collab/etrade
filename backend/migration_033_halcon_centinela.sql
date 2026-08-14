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
