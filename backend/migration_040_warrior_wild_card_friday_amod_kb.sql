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
