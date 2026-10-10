import pandas as pd
from app.rebote_aduana.aduana_climax_manager import AduanaClimaxManager

def test_adaptive_lot_scale_crypto_large():
    pos = {'symbol': 'SOLUSDT', 'size': 10.0, 'market_type': 'crypto_futures'}
    res = AduanaClimaxManager.calculate_adaptive_close_size(pos, 0.40, current_price=100.0, market_type='crypto')
    assert res['action'] == 'PARTIAL'
    assert res['close_qty'] == 4.0
    assert res['remaining_qty'] == 6.0
    assert res['ratio_type'] == 'target_adaptive'

def test_adaptive_lot_scale_crypto_fallback_50():
    # 0.12 SOL a $100 = $12.00.
    # 40% de 0.12 = 0.048 SOL = $4.80 (Menor al min_notional de $5 USD)
    # Por tanto, debe hacer fallback a 50%: 0.06 SOL = $6.00 (>= $5 USD)
    pos = {'symbol': 'SOLUSDT', 'size': 0.12, 'market_type': 'crypto_futures'}
    res = AduanaClimaxManager.calculate_adaptive_close_size(pos, 0.40, current_price=100.0, market_type='crypto')
    assert res['action'] == 'PARTIAL'
    assert res['close_qty'] == 0.06
    assert res['remaining_qty'] == 0.06
    assert res['ratio_type'] == 'fallback_50'

def test_adaptive_lot_scale_crypto_indivisible():
    # 0.06 SOL a $100 = $6.00.
    # Ni 40% ($2.40) ni 50% ($3.00) cumplen el min_notional de $5 USD
    # Por tanto, debe cerrar el 100%
    pos = {'symbol': 'SOLUSDT', 'size': 0.06, 'market_type': 'crypto_futures'}
    res = AduanaClimaxManager.calculate_adaptive_close_size(pos, 0.40, current_price=100.0, market_type='crypto')
    assert res['action'] == 'FULL'
    assert res['close_qty'] == 0.06
    assert res['remaining_qty'] == 0.0
    assert res['ratio_type'] == 'indivisible_100'

def test_adaptive_lot_scale_forex():
    # 0.10 lotes -> 40% es 0.04 lotes
    pos_large = {'symbol': 'EURUSD', 'lots': 0.10, 'market_type': 'forex_futures'}
    res1 = AduanaClimaxManager.calculate_adaptive_close_size(pos_large, 0.40, current_price=1.10, market_type='forex')
    assert res1['action'] == 'PARTIAL'
    assert res1['close_qty'] == 0.04
    assert res1['remaining_qty'] == 0.06

    # 0.02 lotes -> 40% es 0.008 (< 0.01) -> Fallback a 50% (0.01 lotes)
    pos_med = {'symbol': 'EURUSD', 'lots': 0.02, 'market_type': 'forex_futures'}
    res2 = AduanaClimaxManager.calculate_adaptive_close_size(pos_med, 0.40, current_price=1.10, market_type='forex')
    assert res2['action'] == 'PARTIAL'
    assert res2['close_qty'] == 0.01
    assert res2['remaining_qty'] == 0.01
    assert res2['ratio_type'] == 'fallback_50'

    # 0.01 lotes (mínimo indivisible) -> Cierre Total 100%
    pos_min = {'symbol': 'EURUSD', 'lots': 0.01, 'market_type': 'forex_futures'}
    res3 = AduanaClimaxManager.calculate_adaptive_close_size(pos_min, 0.40, current_price=1.10, market_type='forex')
    assert res3['action'] == 'FULL'
    assert res3['close_qty'] == 0.01
    assert res3['ratio_type'] == 'indivisible_100'

def test_evaluate_position_climax_5m_short_proposal_b():
    # Posición SHORT en SOL abierta a $109.06
    pos = {
        'symbol': 'SOLUSDT',
        'side': 'SHORT',
        'entry_price': 109.06,
        'size': 1.0,
        'climax_stage': 0,
        'market_type': 'crypto_futures'
    }
    
    # Mock de memoria con bandas 5m
    # LOWER_5 en $108.60
    memory_mock = {
        'SOLUSDT': {
            '5m': {
                'df': pd.DataFrame([{
                    'close': 108.59, 'basis': 110.0,
                    'upper_5': 111.40, 'upper_6': 111.84,
                    'lower_5': 108.60, 'lower_6': 108.16
                }] * 10)
            }
        }
    }

    # Caso 1: Precio en $108.59 (PnL = +0.43% > 0.40%). Toca LOWER_5 -> Dispara Etapa 1
    res1 = AduanaClimaxManager.evaluate_position_climax(pos, current_price=108.59, memory_store=memory_mock)
    assert res1['triggered'] is True
    assert res1['stage'] == 1
    assert res1['timeframe'] == '5m'
    assert res1['target_close_ratio'] == 0.40
    assert res1['new_sl_be'] < 109.06  # SL en break-even con buffer

    # Caso 2: Precio en $108.80 (PnL = +0.23% < 0.40%). NO debe disparar aunque estuviera cerca
    res2 = AduanaClimaxManager.evaluate_position_climax(pos, current_price=108.80, memory_store=memory_mock)
    assert res2['triggered'] is False

def test_evaluate_position_climax_15m_long_proposal_b():
    # Posición LONG en SOL abierta a $100.00
    pos = {
        'symbol': 'SOLUSDT',
        'side': 'LONG',
        'entry_price': 100.00,
        'size': 1.0,
        'climax_stage': 0,
        'market_type': 'crypto_futures'
    }
    
    # Mock de memoria con bandas 15m
    # UPPER_5 en $100.80
    memory_mock = {
        'SOLUSDT': {
            '15m': {
                'df': pd.DataFrame([{
                    'close': 100.85, 'basis': 100.0,
                    'upper_5': 100.80, 'upper_6': 101.50,
                    'lower_5': 99.20, 'lower_6': 98.50
                }] * 10)
            }
        }
    }

    # Precio en $100.85 (PnL = +0.85% > 0.40%). Toca UPPER_5 en 15m -> Dispara Etapa 2
    res = AduanaClimaxManager.evaluate_position_climax(pos, current_price=100.85, memory_store=memory_mock)
    assert res['triggered'] is True
    assert res['stage'] == 2
    assert res['timeframe'] == '15m'
    assert res['new_sl_be'] > 100.00

def test_evaluate_position_climax_macro_1d():
    pos = {
        'symbol': 'SOLUSDT',
        'side': 'LONG',
        'entry_price': 100.00,
        'size': 1.0,
        'climax_stage': 1,
        'market_type': 'crypto_futures'
    }
    memory_mock = {
        'SOLUSDT': {
            '1d': {
                'df': pd.DataFrame([{
                    'close': 120.0, 'basis': 100.0,
                    'upper_5': 118.0, 'upper_6': 122.0,
                    'lower_5': 82.0, 'lower_6': 78.0
                }] * 10)
            }
        }
    }
    res = AduanaClimaxManager.evaluate_position_climax(pos, current_price=120.0, memory_store=memory_mock)
    assert res['triggered'] is True
    assert res['stage'] == 5
    assert res['action'] == 'FULL'
    assert res['target_close_ratio'] == 1.0

def test_climax_full_close_macro_confluence_short():
    # Posición SHORT en SOL. Precio cae a $108.59 (toca LOWER_5 en 5m)
    # En 1h la EMA3 tiene pendiente positiva y toca Banda Inferior
    pos = {
        'symbol': 'SOLUSDT',
        'side': 'SHORT',
        'entry_price': 109.06,
        'size': 1.0,
        'climax_stage': 0,
        'market_type': 'crypto_futures'
    }
    # 1h dataframe con EMA3 alcista / soporte
    df_1h = pd.DataFrame([
        {'open': 109.5, 'high': 109.6, 'low': 108.8, 'close': 108.9},
        {'open': 108.9, 'high': 109.0, 'low': 108.7, 'close': 108.8},
        {'open': 108.8, 'high': 109.3, 'low': 108.59, 'close': 109.2}  # Cierre verde, pendiente EMA3 > 0
    ])
    df_5m = pd.DataFrame([
        {'open': 109.0, 'high': 109.1, 'low': 108.59, 'close': 108.65,
         'basis': 109.0, 'upper_5': 109.8, 'upper_6': 110.0, 'lower_5': 108.60, 'lower_6': 108.20}
    ] * 5)
    memory_mock = {
        'SOLUSDT': {
            '5m': {'df': df_5m},
            '1h': {'df': df_1h}
        }
    }
    # Precio actual $108.59 (PnL = (109.06 - 108.59)/109.06 = +0.43% >= +0.40%)
    res = AduanaClimaxManager.evaluate_position_climax(pos, current_price=108.59, memory_store=memory_mock)
    assert res['triggered'] is True
    assert res['action'] == 'FULL'
    assert res['target_close_ratio'] == 1.0
    assert res['sar_eligible'] is True
    assert res['sar_direction'] == 'long'
    assert 'soporte/confluencia macro' in res['reason']

def test_climax_partial_close_no_macro_confluence_short():
    # Posición SHORT en SOL. Precio cae a $108.59, pero 1h está cayendo libremente sin soporte
    pos = {
        'symbol': 'SOLUSDT',
        'side': 'SHORT',
        'entry_price': 109.06,
        'size': 1.0,
        'climax_stage': 0,
        'market_type': 'crypto_futures'
    }
    # 1h dataframe bajista continuo
    df_1h = pd.DataFrame([
        {'open': 110.5, 'high': 110.6, 'low': 109.8, 'close': 110.0},
        {'open': 110.0, 'high': 110.1, 'low': 109.2, 'close': 109.4},
        {'open': 109.4, 'high': 109.4, 'low': 108.0, 'close': 108.1}  # Vela roja sólida, sin soporte
    ])
    df_5m = pd.DataFrame([
        {'open': 109.0, 'high': 109.1, 'low': 108.59, 'close': 108.59,
         'basis': 109.0, 'upper_5': 109.8, 'upper_6': 110.0, 'lower_5': 108.60, 'lower_6': 108.20}
    ] * 5)
    memory_mock = {
        'SOLUSDT': {
            '5m': {'df': df_5m},
            '1h': {'df': df_1h}
        }
    }
    res = AduanaClimaxManager.evaluate_position_climax(pos, current_price=108.59, memory_store=memory_mock)
    assert res['triggered'] is True
    assert res['action'] == 'PARTIAL'
    assert res['target_close_ratio'] == 0.40
    assert res['sar_eligible'] is False

def test_climax_sipv_signal_long_sar():
    # Prueba de señal de Giro a LONG con mecha de absorción y SIPV tras cierre de SHORT
    df_1h = pd.DataFrame([
        {'open': 109.0, 'high': 109.2, 'low': 108.6, 'close': 108.7},
        {'open': 108.7, 'high': 109.0, 'low': 108.6, 'close': 108.8},
        {'open': 108.8, 'high': 109.4, 'low': 108.59, 'close': 109.2}  # EMA3 slope > 0
    ])
    # 5m con mecha inferior larga (open 109.0, low 108.59, close 108.95 -> lower wick 0.36 / 0.41 = 87%)
    df_5m = pd.DataFrame([
        {'open': 109.0, 'high': 109.0, 'low': 108.59, 'close': 108.95,
         'basis': 109.0, 'lower_5': 108.60, 'lower_6': 108.20, 'upper_5': 109.8, 'upper_6': 110.0}
    ] * 5)
    df_15m = pd.DataFrame([
        {'open': 109.1, 'high': 109.2, 'low': 108.59, 'close': 108.90,
         'basis': 109.2, 'lower_5': 108.60, 'lower_6': 108.10, 'upper_5': 109.9, 'upper_6': 110.2}
    ] * 5)
    memory_mock = {
        'SOLUSDT': {
            '5m': {'df': df_5m},
            '15m': {'df': df_15m},
            '1h': {'df': df_1h}
        }
    }
    sig = AduanaClimaxManager.evaluate_climax_sipv_signal(
        symbol='SOLUSDT',
        direction='long',
        current_price=108.90,
        memory_store=memory_mock,
        is_sar=True,
        climax_extreme=108.59
    )
    assert sig['triggered'] is True
    assert sig['direction'] == 'long'
    assert sig['rule_code'] == 'REB_CLIMAX_SAR'
    assert sig['suggested_sl'] < 108.59  # SL protegido bajo la mecha
    assert sig['suggested_tp'] >= 109.20  # TP en Basis

def test_climax_sipv_signal_falling_knife_rejected():
    # Prueba del filtro de cuchillo cayendo: vela sólida bajista sin mecha (< 25%)
    df_1h = pd.DataFrame([
        {'open': 109.0, 'high': 109.2, 'low': 108.6, 'close': 108.7},
        {'open': 108.7, 'high': 109.0, 'low': 108.6, 'close': 108.8},
        {'open': 108.8, 'high': 109.4, 'low': 108.59, 'close': 109.2}
    ])
    # 5m vela roja sólida: open 109.0, high 109.0, low 108.59, close 108.60 (mecha inferior = 0.01 / 0.41 = 2.4%)
    df_5m = pd.DataFrame([
        {'open': 109.0, 'high': 109.0, 'low': 108.59, 'close': 108.60,
         'basis': 109.0, 'lower_5': 108.60, 'lower_6': 108.20, 'upper_5': 109.8, 'upper_6': 110.0}
    ] * 5)
    df_15m = pd.DataFrame([
        {'open': 109.1, 'high': 109.1, 'low': 108.59, 'close': 108.60,
         'basis': 109.2, 'lower_5': 108.60, 'lower_6': 108.10, 'upper_5': 109.9, 'upper_6': 110.2}
    ] * 5)
    memory_mock = {
        'SOLUSDT': {
            '5m': {'df': df_5m},
            '15m': {'df': df_15m},
            '1h': {'df': df_1h}
        }
    }
    sig = AduanaClimaxManager.evaluate_climax_sipv_signal(
        symbol='SOLUSDT',
        direction='long',
        current_price=108.60,
        memory_store=memory_mock,
        is_sar=False
    )
    # Debe ser rechazado por filtro de cuchillo cayendo
    assert sig['triggered'] is False
    assert 'cuchillo cayendo' in sig['reason']

def test_climax_sipv_signal_flat_direct():
    # Símbolo en estado FLAT (sin posición previa): toca LOWER_5 con mecha y soporte macro
    df_1h = pd.DataFrame([
        {'open': 109.0, 'high': 109.2, 'low': 108.6, 'close': 108.7},
        {'open': 108.7, 'high': 109.0, 'low': 108.6, 'close': 108.8},
        {'open': 108.8, 'high': 109.4, 'low': 108.59, 'close': 109.2}
    ])
    df_5m = pd.DataFrame([
        {'open': 108.8, 'high': 109.0, 'low': 108.59, 'close': 108.95,
         'basis': 109.0, 'lower_5': 108.60, 'lower_6': 108.20, 'upper_5': 109.8, 'upper_6': 110.0}
    ] * 5)
    df_15m = pd.DataFrame([
        {'open': 109.1, 'high': 109.2, 'low': 108.59, 'close': 108.95,
         'basis': 109.2, 'lower_5': 108.60, 'lower_6': 108.10, 'upper_5': 109.9, 'upper_6': 110.2}
    ] * 5)
    memory_mock = {
        'SOLUSDT': {
            '5m': {'df': df_5m},
            '15m': {'df': df_15m},
            '1h': {'df': df_1h}
        }
    }
    sig = AduanaClimaxManager.evaluate_climax_sipv_signal(
        symbol='SOLUSDT',
        direction='long',
        current_price=108.95,
        memory_store=memory_mock,
        is_sar=False
    )
    assert sig['triggered'] is True
    assert sig['rule_code'] == 'REB_CLIMAX_DIRECT'
    assert sig['suggested_sl'] > 0
    assert sig['suggested_tp'] > sig['suggested_sl']

def test_forex_climax_full_close_and_sar():
    # Forex: Posición SHORT en EURUSD abierta a 1.0850. Precio cae a 1.0800 (+50 pips >= +5 pips)
    pos = {
        'symbol': 'EURUSD',
        'side': 'SHORT',
        'entry_price': 1.0850,
        'lots': 0.10,
        'climax_stage': 0,
        'market_type': 'forex_futures'
    }
    df_1h = pd.DataFrame([
        {'open': 1.0820, 'high': 1.0830, 'low': 1.0795, 'close': 1.0800},
        {'open': 1.0800, 'high': 1.0815, 'low': 1.0795, 'close': 1.0805},
        {'open': 1.0805, 'high': 1.0840, 'low': 1.0795, 'close': 1.0830}  # EMA3 creciente
    ])
    df_5m = pd.DataFrame([
        {'open': 1.0810, 'high': 1.0815, 'low': 1.0798, 'close': 1.0800,
         'basis': 1.0825, 'lower_5': 1.0800, 'lower_6': 1.0780, 'upper_5': 1.0860, 'upper_6': 1.0880}
    ] * 5)
    memory_mock = {
        'EURUSD': {
            '5m': {'df': df_5m},
            '1h': {'df': df_1h}
        }
    }
    res = AduanaClimaxManager.evaluate_position_climax(pos, current_price=1.0800, memory_store=memory_mock)
    assert res['triggered'] is True
    assert res['action'] == 'FULL'
    assert res['sar_eligible'] is True
    assert res['sar_direction'] == 'long'

if __name__ == '__main__':
    test_adaptive_lot_scale_crypto_large()
    test_adaptive_lot_scale_crypto_fallback_50()
    test_adaptive_lot_scale_crypto_indivisible()
    test_adaptive_lot_scale_forex()
    test_evaluate_position_climax_5m_short_proposal_b()
    test_evaluate_position_climax_15m_long_proposal_b()
    test_evaluate_position_climax_macro_1d()
    test_climax_full_close_macro_confluence_short()
    test_climax_partial_close_no_macro_confluence_short()
    test_climax_sipv_signal_long_sar()
    test_climax_sipv_signal_falling_knife_rejected()
    test_climax_sipv_signal_flat_direct()
    test_forex_climax_full_close_and_sar()
    print("\n🎉 ALL UNIT TESTS PASSED SUCCESSFULLY! (13/13)")


