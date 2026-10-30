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
