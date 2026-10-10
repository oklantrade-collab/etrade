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

if __name__ == '__main__':
    test_adaptive_lot_scale_crypto_large()
    print("✓ test_adaptive_lot_scale_crypto_large passed")
    test_adaptive_lot_scale_crypto_fallback_50()
    print("✓ test_adaptive_lot_scale_crypto_fallback_50 passed")
    test_adaptive_lot_scale_crypto_indivisible()
    print("✓ test_adaptive_lot_scale_crypto_indivisible passed")
    test_adaptive_lot_scale_forex()
    print("✓ test_adaptive_lot_scale_forex passed")
    test_evaluate_position_climax_5m_short_proposal_b()
    print("✓ test_evaluate_position_climax_5m_short_proposal_b passed")
    test_evaluate_position_climax_15m_long_proposal_b()
    print("✓ test_evaluate_position_climax_15m_long_proposal_b passed")
    test_evaluate_position_climax_macro_1d()
    print("✓ test_evaluate_position_climax_macro_1d passed")
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! (7/7)")

