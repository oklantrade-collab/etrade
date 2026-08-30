"""
Tests unitarios para ANCLA Manager
"""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
from app.strategy.ancla_manager import AnclaManager

def create_mock_15m_df(price=100.0, ema_slope=-0.5, is_high_vol=False):
    n = 40
    df = pd.DataFrame(index=range(n))
    df['close'] = [price + i*0.1 for i in range(n)]
    df['open'] = [price + i*0.1 for i in range(n)]
    df['high'] = [price + i*0.1 + 0.5 for i in range(n)]
    df['low'] = [price + i*0.1 - 0.5 for i in range(n)]
    
    # EMA3 con pendiente configurada
    df['ema_3'] = [price + i*ema_slope for i in range(n)]
    
    # ATR
    atr_val = 2.5 if is_high_vol else 0.8
    df['atr'] = atr_val
    return df

def create_mock_macro_df(price=100.0):
    n = 30
    df = pd.DataFrame(index=range(n))
    df['close'] = [price + i*0.5 for i in range(n)]
    df['open'] = [price + i*0.5 for i in range(n)]
    df['high'] = [price + i*0.5 + 1.0 for i in range(n)]
    df['low'] = [price + i*0.5 - 1.0 for i in range(n)]
    df['upper_2'] = price + 10.0
    df['upper_1'] = price + 5.0
    df['lower_1'] = price - 5.0
    df['lower_2'] = price - 10.0
    df['ema_3'] = [price + i*(-0.2) for i in range(n)] # EMA3 descendente (agotamiento)
    return df

def test_ancla_sl_dynamic_arming_long():
    manager = AnclaManager()
    df_15m = create_mock_15m_df(price=96.0, ema_slope=-0.2)
    fib_levels = {
        'lower_2': 90.0,
        'lower_1': 95.0,
        'basis': 100.0,
        'upper_1': 105.0,
        'upper_2': 110.0,
    }
    # Precio 96.0 está en zona [lower_1=95.0, basis=100.0]. Punto medio = 97.5.
    # 96.0 <= 97.5 (mitad inferior) + EMA3 descendente -> Debe armar SL
    position = {
        'id': 'pos_1',
        'symbol': 'BTCUSDT',
        'side': 'long',
        'current_price': 96.0,
        'ancla_sl_armado': False,
    }
    
    res = manager.calculate_sl_dynamic(position, df_15m, fib_levels)
    assert res['armed'] is True
    assert res['sl_price'] < 95.0  # Menor a lower_bound (95.0) por el buffer
    assert "ANCLA SL LONG Armado" in res['reason']

def test_ancla_sl_hysteresis_disarm():
    manager = AnclaManager()
    # EMA3 ascendente en las últimas 2 velas
    df_15m = create_mock_15m_df(price=98.0, ema_slope=0.5)
    fib_levels = {'lower_1': 95.0, 'basis': 100.0, 'upper_1': 105.0}
    
    position = {
        'id': 'pos_1',
        'symbol': 'BTCUSDT',
        'side': 'long',
        'current_price': 98.0,
        'ancla_sl_armado': True, # Ya estaba armado
    }
    
    res = manager.calculate_sl_dynamic(position, df_15m, fib_levels)
    assert res['armed'] is False
    assert "Desarmado por histéresis" in res['reason']

def test_ancla_tp1_and_tp2_flow():
    manager = AnclaManager()
    df_1D = create_mock_macro_df(price=100.0)
    df_4H = create_mock_macro_df(price=100.0)
    
    position = {
        'id': 'pos_1',
        'symbol': 'ETHUSDT',
        'side': 'long',
        'current_price': 102.0,
        'volume': 1.0,
        'ancla_tp1_fired': False,
        'ancla_tp1_placed': False,
    }
    
    # 1. Evaluación de TP1
    tp1_res = manager.calculate_tp1_stage(position, df_1D, df_4H, min_broker_lot=0.01)
    assert tp1_res['should_place_tp1'] is True
    assert tp1_res['tp1_price'] > 102.0
    assert tp1_res['volume_pct'] == 50.0
    
    # 2. Evaluación de TP2 cuando TP1 ya ejecutó
    position['ancla_tp1_fired'] = True
    tp2_res = manager.calculate_tp2_stage(position, df_1D)
    assert tp2_res['should_place_tp2'] is True
    assert tp2_res['tp2_price'] > 100.0
    assert tp2_res['volume_pct'] == 100.0

def test_ancla_breakeven_post_tp1():
    manager = AnclaManager()
    pos_crypto = {'entry_price': 50000.0, 'side': 'long', 'symbol': 'BTCUSDT'}
    be_crypto = manager.calculate_breakeven_sl_post_tp1(pos_crypto, is_forex=False)
    assert be_crypto == 50000.0 * 1.0015
    
    pos_forex = {'entry_price': 1.0850, 'side': 'long', 'symbol': 'EURUSD'}
    be_forex = manager.calculate_breakeven_sl_post_tp1(pos_forex, is_forex=True)
    assert be_forex == 1.0850 + (3.0 * 0.0001)

if __name__ == '__main__':
    print("Ejecutando tests de ANCLA Manager...")
    test_ancla_sl_dynamic_arming_long()
    print("[PASS] test_ancla_sl_dynamic_arming_long")
    test_ancla_sl_hysteresis_disarm()
    print("[PASS] test_ancla_sl_hysteresis_disarm")
    test_ancla_tp1_and_tp2_flow()
    print("[PASS] test_ancla_tp1_and_tp2_flow")
    test_ancla_breakeven_post_tp1()
    print("[PASS] test_ancla_breakeven_post_tp1")
    print("\n>>> TODOS LOS TESTS DE ANCLA MANAGER PASARON EXITOSAMENTE! <<<")
