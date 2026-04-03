-- migration_013_parameter_bounds.sql
-- Sistema de Guardrails de Parámetros para eTrade v3

-- Tabla de límites por parámetro
CREATE TABLE IF NOT EXISTS parameter_bounds (
    parameter_name      VARCHAR(50)  PRIMARY KEY,
    category            VARCHAR(20)  NOT NULL,
    -- Valores: 'risk' | 'entry' | 'sizing' | 'timing' | 'technical'

    min_value           NUMERIC(10,4) NOT NULL,
    max_value           NUMERIC(10,4) NOT NULL,
    default_value       NUMERIC(10,4) NOT NULL,
    current_value       NUMERIC(10,4) NOT NULL,

    description         TEXT,
    unit                VARCHAR(20),    -- 'ratio' | 'multiplier' | 'pct' | 'bars' | 'float'
    regime              VARCHAR(20),    -- 'bajo_riesgo' | 'riesgo_medio' | 'alto_riesgo' | 'all'

    requires_approval_outside_bounds  BOOLEAN DEFAULT true,
    last_changed_at     TIMESTAMPTZ DEFAULT NOW(),
    last_changed_by     VARCHAR(50),    -- 'system' | 'antigravity' | 'jhon'
    change_reason       TEXT,

    -- Performance al momento del último cambio
    perf_win_rate_before    NUMERIC(5,4),
    perf_win_rate_after     NUMERIC(5,4),
    perf_ev_before          NUMERIC(8,4),   -- expected value antes del cambio
    perf_ev_after           NUMERIC(8,4),   -- expected value después del cambio

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Historial de todos los cambios (audit trail)
CREATE TABLE IF NOT EXISTS parameter_changes_log (
    id              BIGSERIAL PRIMARY KEY,
    parameter_name  VARCHAR(50) REFERENCES parameter_bounds(parameter_name),
    old_value       NUMERIC(10,4),
    new_value       NUMERIC(10,4),
    changed_at      TIMESTAMPTZ DEFAULT NOW(),
    changed_by      VARCHAR(50),
    change_reason   TEXT,
    within_bounds   BOOLEAN,
    approved_by     VARCHAR(50),    -- null si dentro de bounds, 'jhon' si fuera
    backtest_ev     NUMERIC(8,4),   -- expected value del backtest que justificó el cambio
    accepted        BOOLEAN
);

-- SEED INICIAL 
INSERT INTO parameter_bounds
    (parameter_name, category, min_value, max_value, default_value, current_value,
     description, unit, regime)
VALUES

-- ═══ PARÁMETROS DE RIESGO (RR mínimo) ═══
('rr_min_bajo_riesgo',     'risk', 1.5, 4.0, 2.0, 2.0,
 'RR mínimo aceptable en régimen bajo riesgo. < 1.5 destruye esperanza matemática con 50% win rate.',
 'ratio', 'bajo_riesgo'),

('rr_min_riesgo_medio',    'risk', 1.5, 4.0, 2.5, 2.5,
 'RR mínimo aceptable en régimen riesgo medio. Mayor que bajo_riesgo para compensar el mayor ATR.',
 'ratio', 'riesgo_medio'),

('rr_min_alto_riesgo',     'risk', 2.0, 4.0, 3.0, 3.0,
 'RR mínimo aceptable en régimen alto riesgo. El más exigente por la mayor volatilidad.',
 'ratio', 'alto_riesgo'),

-- ═══ PARÁMETROS DE RIESGO (SL — multiplicador ATR) ═══
('atr_mult_bajo_riesgo',   'risk', 1.0, 3.5, 1.5, 1.5,
 'Multiplicador del ATR para calcular el Stop Loss en bajo riesgo. SL = entry - (ATR × mult).',
 'multiplier', 'bajo_riesgo'),

('atr_mult_riesgo_medio',  'risk', 1.0, 3.5, 2.0, 2.0,
 'Multiplicador del ATR para calcular el Stop Loss en riesgo medio.',
 'multiplier', 'riesgo_medio'),

('atr_mult_alto_riesgo',   'risk', 1.0, 3.5, 2.5, 2.5,
 'Multiplicador del ATR para calcular el Stop Loss en alto riesgo.',
 'multiplier', 'alto_riesgo'),

-- ═══ PARÁMETROS DE ENTRADA (MTF threshold) ═══
('mtf_threshold_bajo',     'entry', 0.45, 0.90, 0.50, 0.50,
 'Umbral de alineación multi-timeframe en bajo riesgo. Al menos 50% de TFs alineados.',
 'pct', 'bajo_riesgo'),

('mtf_threshold_medio',    'entry', 0.45, 0.90, 0.65, 0.65,
 'Umbral de alineación multi-timeframe en riesgo medio. Al menos 65% de TFs alineados.',
 'pct', 'riesgo_medio'),

('mtf_threshold_alto',     'entry', 0.45, 0.90, 0.80, 0.80,
 'Umbral de alineación multi-timeframe en alto riesgo. Al menos 80% de TFs alineados.',
 'pct', 'alto_riesgo'),

-- ═══ PARÁMETROS TÉCNICOS (EMA20 phases) ═══
('ema20_flat_pct_bajo',    'technical', 10.0, 30.0, 15.0, 15.0,
 'Percentil que define zona plana del EMA20 en bajo riesgo.',
 'pct', 'bajo_riesgo'),

('ema20_flat_pct_medio',   'technical', 10.0, 30.0, 20.0, 20.0,
 'Percentil que define zona plana del EMA20 en riesgo medio.',
 'pct', 'riesgo_medio'),

('ema20_flat_pct_alto',    'technical', 10.0, 30.0, 25.0, 25.0,
 'Percentil que define zona plana del EMA20 en alto riesgo.',
 'pct', 'alto_riesgo'),

('ema20_peak_pct_bajo',    'technical', 70.0, 90.0, 85.0, 85.0,
 'Percentil que define zona de cima del EMA20 en bajo riesgo.',
 'pct', 'bajo_riesgo'),

('ema20_peak_pct_medio',   'technical', 70.0, 90.0, 80.0, 80.0,
 'Percentil que define zona de cima del EMA20 en riesgo medio.',
 'pct', 'riesgo_medio'),

('ema20_peak_pct_alto',    'technical', 70.0, 90.0, 75.0, 75.0,
 'Percentil que define zona de cima del EMA20 en alto riesgo.',
 'pct', 'alto_riesgo'),

-- ═══ PARÁMETROS DE TIMING (cooldown y holding) ═══
('post_sl_cooldown_bars',  'timing', 1, 10, 3, 3,
 'Velas de cooldown después de un SL. Evita revenge trading automático.',
 'bars', 'all'),

('post_tp_cooldown_bars',  'timing', 0, 5,  1, 1,
 'Velas de cooldown después de un TP.',
 'bars', 'all'),

('signal_max_age_bars',    'timing', 1, 10, 3, 3,
 'Máximo de barras que puede tener una señal del PineScript antes de expirar.',
 'bars', 'all'),

-- ═══ PARÁMETROS DE SIZING ═══
('capital_pct_for_trading','sizing', 5.0, 50.0, 20.0, 20.0,
 '% del capital total destinado a trading. El 80% restante permanece como reserva.',
 'pct', 'all'),

('fee_pct',                'sizing', 0.001, 0.002, 0.001, 0.001,
 'Fee estimado de Binance por operación (0.1% maker/taker).',
 'float', 'all'),

-- ═══ PROTECCIONES DE RIESGO ═══
('max_daily_loss_pct',     'risk', 2.0, 15.0, 5.0, 5.0,
 '% máximo de pérdida diaria sobre capital total antes de activar circuit breaker.',
 'pct', 'all'),

('max_trade_loss_pct',     'risk', 0.5, 5.0, 2.0, 2.0,
 '% máximo de pérdida por trade individual sobre capital total.',
 'pct', 'all'),

('emergency_atr_mult',     'risk', 1.5, 4.0, 2.0, 2.0,
 'Multiplicador del ATR promedio que activa el monitor de emergencia vía WebSocket.',
 'multiplier', 'all')

ON CONFLICT (parameter_name) DO NOTHING;
