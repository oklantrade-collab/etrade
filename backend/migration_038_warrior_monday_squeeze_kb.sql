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
