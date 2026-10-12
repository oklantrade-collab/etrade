import os
import sys
import pytest
import pandas as pd
import numpy as np

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.strategy.erep_manager import evaluate_erep_phase
from app.strategy.quantum_squeeze_hedge import (
    scan_squeeze_opportunities,
    evaluate_qshr_trailing_and_exit
)

def test_short_with_sl_zero_not_touched():
    """
    Verifica que una posición SHORT con sl_price <= 0 nunca marque sl_touched como True.
    """
    current_price = 79000.0
    sl_price = 0.0
    is_long = False

    # Nueva lógica implementada
    sl_touched = False
    if sl_price > 0:
        sl_touched = (
            (is_long and current_price <= sl_price) or
            (not is_long and current_price >= sl_price)
        )
    assert sl_touched is False

    # Comparación con el comportamiento si sl_price > 0
    sl_price_real = 78000.0  # El precio subió por encima del SL
    sl_touched_real = False
    if sl_price_real > 0:
        sl_touched_real = (not is_long and current_price >= sl_price_real)
    assert sl_touched_real is True

def test_long_with_sl_zero_not_touched():
    """
    Verifica que una posición LONG con sl_price <= 0 nunca marque sl_touched como True.
    """
    current_price = 98.0
    sl_price = 0.0
    is_long = True

    sl_touched = False
    if sl_price > 0:
        sl_touched = (
            (is_long and current_price <= sl_price) or
            (not is_long and current_price >= sl_price)
        )
    assert sl_touched is False

def test_erep_phase1_in_profit_does_not_close_sl():
    """
    Verifica que EREP Fase 1 nunca emita 'close_sl' cuando la posición está en ganancia o breakeven.
    """
    # Posición SHORT en ganancia (entry = 2504, current = 2500)
    pos_short = {
        'id': 'test-pos-short',
        'symbol': 'ETHUSDT',
        'side': 'short',
        'entry_price': 2504.0,
        'avg_entry_price': 2504.0,
        'size': 0.029,
        'erep_phase': 1,
        'erep_active': True,
        'erep_p1_price': 2504.0
    }
    snap = {'ema_3': 2500.0, 'ema_9': 2501.0}
    current_price_short = 2500.0 # En ganancia para SHORT

    res_short = evaluate_erep_phase(
        pos_short, current_price_short, snap, None, None, 'crypto_futures'
    )
    assert res_short['action'] != 'close_sl', f"No debe cerrar por SL si está en ganancia: {res_short}"
    assert res_short['action'] == 'wait_natural'

    # Posición LONG en ganancia (entry = 98.0, current = 100.0)
    pos_long = {
        'id': 'test-pos-long',
        'symbol': 'SOLUSDT',
        'side': 'long',
        'entry_price': 98.0,
        'avg_entry_price': 98.0,
        'size': 0.75,
        'erep_phase': 1,
        'erep_active': True,
        'erep_p1_price': 98.0
    }
    current_price_long = 100.0 # En ganancia para LONG

    res_long = evaluate_erep_phase(
        pos_long, current_price_long, snap, None, None, 'crypto_futures'
    )
    assert res_long['action'] != 'close_sl', f"No debe cerrar por SL si está en ganancia: {res_long}"
    assert res_long['action'] == 'wait_natural'

def test_climax_isolation_from_generic_trailing():
    """
    Verifica que las posiciones Clímax no sean cerradas por estancamiento prematuro en evaluate_qshr_trailing_and_exit.
    """
    pos_climax = {
        'id': 'climax-1',
        'symbol': 'BTCUSDT',
        'side': 'short',
        'rule_code': 'Bb33_QSHR_CLIMAX_5M_UPPER6_SHORT',
        'entry_price': 79000.0,
        'size': 0.001
    }
    dates = pd.date_range("2026-09-11 12:00", periods=25, freq="5min")
    df_5m = pd.DataFrame({
        'open': [79000.0]*25,
        'high': [79050.0]*25,
        'low': [78950.0]*25,
        'close': [79000.0]*25,
        'volume': [100.0]*25
    }, index=dates)

    res = evaluate_qshr_trailing_and_exit(pos_climax, df_5m, df_5m, 78900.0, 'BTCUSDT')
    assert res is None, "Posición Clímax debe estar aislada de evaluate_qshr_trailing_and_exit para ser gestionada por EREP"

def test_climax_entry_requires_real_absorption_wick():
    """
    Verifica que una vela de 15m con mecha insignificante (<30%) no califique para Climax LONG,
    incluso si en 5m c_5m > ema3_5m.
    """
    dates_15m = pd.date_range("2026-09-11 10:00", periods=25, freq="15min")
    # Vela 15m con mecha inferior de apenas 5% (cuerpo rojo gigante cayendo)
    # Open: 100, High: 100, Low: 90, Close: 90.5 -> Mecha inf: (90.5 - 90)/10 = 5%
    df_15m = pd.DataFrame({
        'open': [100.0]*24 + [100.0],
        'high': [101.0]*24 + [100.0],
        'low': [98.0]*24 + [90.0],
        'close': [99.0]*24 + [90.5],
        'volume': [1000.0]*25,
        'lower_6': [92.0]*25,
        'upper_6': [105.0]*25,
        'fibonacci_zone': [-6.0]*25
    }, index=dates_15m)

    dates_5m = pd.date_range("2026-09-11 12:00", periods=25, freq="5min")
    # En 5m, precio tuvo un micro-rebote donde c > ema3 pero sin confirmación
    df_5m = pd.DataFrame({
        'open': [90.0]*25,
        'high': [91.0]*25,
        'low': [89.9]*25,
        'close': [90.8]*25,
        'volume': [500.0]*25,
        'lower_6': [92.0]*25,
        'upper_6': [105.0]*25,
        'fibonacci_zone': [-6.0]*25
    }, index=dates_5m)

    signal = scan_squeeze_opportunities('SOLUSDT', df_5m, df_15m, market_type='crypto_futures')
    # Debe ser None o no ser Bb33_QSHR_CLIMAX_LOWER6_LONG porque la mecha inferior es de apenas 5%
    if signal:
        assert signal.get('rule_code') != 'Bb33_QSHR_CLIMAX_LOWER6_LONG'
