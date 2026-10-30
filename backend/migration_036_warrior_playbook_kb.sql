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
