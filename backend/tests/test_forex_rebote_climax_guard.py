import pytest
import pandas as pd
import numpy as np
from app.strategy.profit_capture import evaluate_dynamic_tp_v6, evaluate_mtf_trend_guard
from app.rebote_aduana.rebote_engine import ReboteEngine
from app.rebote_aduana.aduana_exit_gate import AduanaExitGatekeeper, ExitOrderRequest

def create_forex_bars(prices):
    return pd.DataFrame({
        'open': prices,
        'high': [p + 0.0005 for p in prices],
        'low': [p - 0.0005 for p in prices],
        'close': prices,
        'volume': [1000] * len(prices)
    })

def test_forex_long_trend_guard_blocks_premature_exits():
    """Valida que un LONG de Forex con EMA3 > EMA9 en 15m y 5m bloquee salidas anticipadas."""
    # Tendencia alcista en EURUSD
    prices_15m = [1.1500 + i * 0.0004 for i in range(30)] # 15m alcista
    prices_5m = [1.1600 + i * 0.0002 for i in range(30)]  # 5m alcista
    df_15m = create_forex_bars(prices_15m)
    df_5m = create_forex_bars(prices_5m)

    guard_res = evaluate_mtf_trend_guard(
        symbol='EURUSD',
        side='long',
        current_price=1.1620,
        df_15m=df_15m,
        df_5m=df_5m,
        market_type='forex_futures'
    )
    
    assert guard_res['should_block'] is True
    assert "Blindaje" in guard_res['reason']

def test_forex_dynamic_tp_blocks_sub_10_pips():
    """Valida que Dynamic TP v6 no active salidas con ganancias ínfimas (ej. +2.0 pips)."""
    prices_15m = [1.1500 + i * 0.0001 for i in range(30)]
    df_15m = create_forex_bars(prices_15m)
    
    res = evaluate_dynamic_tp_v6(
        symbol='EURUSD',
        side='long',
        current_price=1.1502, # Apenas +2.0 pips
        entry_price=1.1500,
        df_15m=df_15m,
        market_type='forex_futures'
    )
    
    # Debe mantener HOLD_TREND porque pips < 12.0
    assert res['should_close'] is False
    assert res['rule_code'] == 'HOLD_TREND'

def test_forex_rebote_climax_exit_at_extreme_lower():
    """Valida que un SHORT de Forex toque LOWER_5/6 y active salida de clímax con ganancias sustanciales."""
    engine = ReboteEngine()
    
    # Serie de precios en caída en GBPUSD
    prices_15m = [1.3600 - i * 0.0008 for i in range(25)]
    prices_15m[-1] = 1.3410 # Rebote técnico en el piso
    df_15m = create_forex_bars(prices_15m)
    df_5m = create_forex_bars(prices_15m[-10:])
    
    snap = {
        'lower_5': 1.3420,
        'lower_6': 1.3400,
    }
    
    pos = {
        'id': 'fx-pos-gbp-short',
        'symbol': 'GBPUSD',
        'side': 'short',
        'entry_price': 1.3600,
        'size': 1.0,
        'lots': 0.1
    }
    
    should_exit, reason, meta = engine.evaluate_climax_exit(
        symbol='GBPUSD',
        direction='short',
        current_price=1.3410, # +190 pips de caída
        df_15m=df_15m,
        df_5m=df_5m,
        position=pos,
        snap=snap
    )
    
    assert should_exit is True
    assert "SHORT_LOWER_REBOUND" in meta.get("climax_type", "")
