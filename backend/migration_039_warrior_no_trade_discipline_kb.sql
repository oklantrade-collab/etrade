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
