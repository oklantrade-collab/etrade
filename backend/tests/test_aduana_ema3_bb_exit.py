"""
Test Suite: ADUANA Trend Exit con Doble Validación en Bandas Bollinger (1h / 4h) y Trailing Stop 1h
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import pandas as pd
import numpy as np

from app.rebote_aduana.aduana_trend_exit import evaluate_aduana_trend_exit
from app.strategy.capital_protection import evaluate_trailing_stop, ProtectionState


def create_mock_1h_df(
    ema3_values,
    ema9_values,
    upper_values,
    lower_values,
    close_values=None,
    low_values=None,
    high_values=None
):
    n = len(ema3_values)
    close_vals = close_values if close_values is not None else [100.0] * n
    low_vals = low_values if low_values is not None else [98.0] * n
    high_vals = high_values if high_values is not None else [102.0] * n
    
    data = {
        'close': close_vals,
        'low': low_vals,
        'high': high_vals,
        'ema_3': ema3_values,
        'ema_9': ema9_values,
        'upper_2': upper_values,
        'lower_2': lower_values,
    }
    return pd.DataFrame(data)


# ── TEST 1: LONG FULL CLOSE 1H ──
def test_long_full_close_1h():
    """
    LONG: EMA3 se vuelve plana/negativa (105 -> 104) y Upper BB también se vuelve plana/negativa (110 -> 109.5).
    Debe gatillar FULL_CLOSE (100%).
    """
    df_1h = create_mock_1h_df(
        ema3_values=[100, 102, 105, 104.5],  # 105 -> 104.5 (negativa)
        ema9_values=[98, 99, 100, 101],       # EMA3 > EMA9
        upper_values=[106, 108, 110, 109.8], # 110 -> 109.8 (negativa)
        lower_values=[94, 94, 94, 94],
    )
    pos = {
        'id': 'pos_1',
        'symbol': 'BTCUSDT',
        'side': 'long',
        'entry_price': 100.0,
        'size': 1.0,
        'partial_closed': False
    }
    res = evaluate_aduana_trend_exit(pos, current_price=104.0, df_1h=df_1h)
    assert res['action'] == 'FULL_CLOSE'
    assert 'Doble validación cumplida' in res['reason']


# ── TEST 2: LONG PARTIAL CLOSE 50% 1H ──
def test_long_partial_close_50_1h():
    """
    LONG: EMA3 se vuelve plana/negativa (105 -> 104.8), pero Upper BB sigue expandiéndose hacia arriba (110 -> 112).
    Debe gatillar PARTIAL_CLOSE_50 (50%).
    """
    df_1h = create_mock_1h_df(
        ema3_values=[100, 102, 105, 104.8],  # 105 -> 104.8 (frenó)
        ema9_values=[98, 99, 100, 101],       # EMA3 > EMA9
        upper_values=[106, 108, 110, 112.0], # 110 -> 112 (expansión activa)
        lower_values=[94, 94, 94, 94],
    )
    pos = {
        'id': 'pos_2',
        'symbol': 'ETHUSDT',
        'side': 'long',
        'entry_price': 100.0,
        'size': 1.0,
        'partial_closed': False
    }
    res = evaluate_aduana_trend_exit(pos, current_price=104.5, df_1h=df_1h)
    assert res['action'] == 'PARTIAL_CLOSE_50'
    assert 'Upper BB sigue expandiendo' in res['reason']


# ── TEST 3: LONG HOLD TREND RUNNING ──
def test_long_hold_trend_running():
    """
    LONG: EMA3 > EMA9 y EMA3 sigue apuntando hacia arriba con fuerza (105 -> 107).
    Debe gatillar HOLD (dejar correr tendencia).
    """
    df_1h = create_mock_1h_df(
        ema3_values=[100, 102, 105, 107.0],  # Positiva ascendente
        ema9_values=[98, 99, 100, 102],       # EMA3 > EMA9
        upper_values=[106, 108, 110, 112],
        lower_values=[94, 94, 94, 94],
    )
    pos = {
        'id': 'pos_3',
        'symbol': 'SOLUSDT',
        'side': 'long',
        'entry_price': 100.0,
        'size': 1.0,
        'partial_closed': False
    }
    res = evaluate_aduana_trend_exit(pos, current_price=106.8, df_1h=df_1h)
    assert res['action'] == 'HOLD'
    assert 'Tendencia activa' in res['reason']


# ── TEST 4: SHORT FULL CLOSE 1H ──
def test_short_full_close_1h():
    """
    SHORT: EMA3 frena la caída y se vuelve plana/positiva (95 -> 95.5)
    y Lower BB también frena la caída (90 -> 90.5).
    Debe gatillar FULL_CLOSE (100%).
    """
    df_1h = create_mock_1h_df(
        ema3_values=[100, 98, 95, 95.5],     # 95 -> 95.5 (positiva/plana)
        ema9_values=[102, 101, 100, 99],     # EMA3 < EMA9
        upper_values=[106, 106, 106, 106],
        lower_values=[94, 92, 90, 90.5],     # 90 -> 90.5 (dejó de caer)
    )
    pos = {
        'id': 'pos_4',
        'symbol': 'BTCUSDT',
        'side': 'short',
        'entry_price': 100.0,
        'size': 1.0,
        'partial_closed': False
    }
    res = evaluate_aduana_trend_exit(pos, current_price=96.0, df_1h=df_1h)
    assert res['action'] == 'FULL_CLOSE'
    assert 'Doble validación cumplida' in res['reason']


# ── TEST 5: SHORT PARTIAL CLOSE 50% 1H ──
def test_short_partial_close_50_1h():
    """
    SHORT: EMA3 frena (95 -> 95.2), pero Lower BB sigue abriéndose violentamente hacia abajo (90 -> 88).
    Debe gatillar PARTIAL_CLOSE_50 (50%).
    """
    df_1h = create_mock_1h_df(
        ema3_values=[100, 98, 95, 95.2],     # Frenó
        ema9_values=[102, 101, 100, 99],     # EMA3 < EMA9
        upper_values=[106, 106, 106, 106],
        lower_values=[94, 92, 90, 88.0],     # Sigue expandiendo hacia abajo
    )
    pos = {
        'id': 'pos_5',
        'symbol': 'ADAUSDT',
        'side': 'short',
        'entry_price': 100.0,
        'size': 1.0,
        'partial_closed': False
    }
    res = evaluate_aduana_trend_exit(pos, current_price=95.5, df_1h=df_1h)
    assert res['action'] == 'PARTIAL_CLOSE_50'
    assert 'Lower BB sigue expandiendo' in res['reason']


# ── TEST 6: MACRO 4H FULL CLOSE CONFIRMATION ──
def test_macro_4h_full_close():
    """
    Posición con parcial tomado previamente (partial_closed=True).
    En 4h se agota la tendencia (EMA3 y Upper BB planas o negativas).
    Debe cerrar el 100% restante.
    """
    df_1h = create_mock_1h_df(
        ema3_values=[100, 102, 104, 104.1],
        ema9_values=[98, 99, 100, 101],
        upper_values=[106, 108, 110, 112],
        lower_values=[94, 94, 94, 94],
    )
    df_4h = create_mock_1h_df(
        ema3_values=[95, 100, 105, 104.8],   # 4h agotado
        ema9_values=[90, 94, 98, 101],
        upper_values=[100, 105, 110, 109.8], # 4h Upper BB agotada
        lower_values=[90, 90, 90, 90],
    )
    pos = {
        'id': 'pos_6',
        'symbol': 'EURUSD',
        'side': 'long',
        'entry_price': 1.0500,
        'size': 1.0,
        'partial_closed': True
    }
    res = evaluate_aduana_trend_exit(pos, current_price=1.0600, df_1h=df_1h, df_4h=df_4h)
    assert res['action'] == 'FULL_CLOSE'
    assert 'Agotamiento macro confirmado' in res['reason']


# ── TEST 7: 1H TRAILING STOP STRUCTURAL SUPPORT (LONG) ──
def test_trailing_stop_1h_updates_sl_long():
    """
    Trailing Stop 1h eleva el SL al soporte estructural de 1h (mínimo de la vela 1h previa o EMA9 de 1h).
    """
    df_1h = create_mock_1h_df(
        ema3_values=[100, 102, 105, 108],
        ema9_values=[98, 99, 102, 104],       # EMA9 = 104
        upper_values=[105, 108, 110, 112],
        lower_values=[95, 95, 95, 95],
        low_values=[97, 98, 103, 105],        # Low previo = 103
    )
    state = ProtectionState(
        position_id='pos_trail_long',
        symbol='BTCUSDT',
        side='long',
        entry_price=100.0,
        original_sl=95.0,
        current_sl=98.0,
        market_type='crypto_futures',
    )
    trail = evaluate_trailing_stop(state, current_price=107.0, df_1h=df_1h)
    assert trail['action'] == 'update_sl'
    assert trail['new_sl'] == 104.0  # max(103, 104) = 104.0
    assert 'Trailing Stop 1h' in trail['reason']


# ── TEST 8: 1H TRAILING STOP STRUCTURAL RESISTANCE (SHORT) ──
def test_trailing_stop_1h_updates_sl_short():
    """
    Trailing Stop 1h desciende el SL a la resistencia estructural de 1h.
    """
    df_1h = create_mock_1h_df(
        ema3_values=[100, 98, 95, 92],
        ema9_values=[102, 101, 98, 96],       # EMA9 = 96
        upper_values=[105, 105, 105, 105],
        lower_values=[95, 92, 90, 88],
        high_values=[103, 102, 97, 95],       # High previo = 97
    )
    state = ProtectionState(
        position_id='pos_trail_short',
        symbol='BTCUSDT',
        side='short',
        entry_price=100.0,
        original_sl=105.0,
        current_sl=102.0,
        market_type='crypto_futures',
    )
    trail = evaluate_trailing_stop(state, current_price=93.0, df_1h=df_1h)
    assert trail['action'] == 'update_sl'
    assert trail['new_sl'] == 96.0  # min(97, 96) = 96.0
    assert 'Trailing Stop 1h' in trail['reason']


# ── TEST 9: HARD SL PRESERVATION WHEN IN LOSS ──
def test_hard_sl_preservation_when_loss():
    """
    Si la posición está en pérdida (o no supera umbral de ganancia),
    ADUANA trend exit NO interfiere ni fuerza cierres anticipados descalibrados.
    Retorna HOLD para que el Hard SL estructural gobierne la gestión del riesgo.
    """
    df_1h = create_mock_1h_df(
        ema3_values=[100, 99, 98, 97],
        ema9_values=[100, 99.5, 99, 98.5],
        upper_values=[105, 105, 105, 105],
        lower_values=[95, 95, 95, 95],
    )
    pos = {
        'id': 'pos_loss',
        'symbol': 'BTCUSDT',
        'side': 'long',
        'entry_price': 100.0,
        'size': 1.0,
        'partial_closed': False
    }
    # Precio actual = 98.5 (PnL = -1.5%)
    res = evaluate_aduana_trend_exit(pos, current_price=98.5, df_1h=df_1h)
    assert res['action'] == 'HOLD'
    assert 'no supera umbral mínimo de ganancia' in res['reason']
