import pytest
import pandas as pd
import numpy as np
from app.rebote_aduana.rebote_engine import ReboteEngine
from app.rebote_aduana.aduana_exit_gate import AduanaExitGatekeeper, ExitOrderRequest

def create_bars(prices):
    return pd.DataFrame({
        'open': prices,
        'high': [p + 0.1 for p in prices],
        'low': [p - 0.1 for p in prices],
        'close': prices,
        'volume': [1000] * len(prices)
    })

def test_short_rebote_climax_exit_at_lower_band():
    """Valida que un SHORT en caída extrema hacia LOWER_5/6 emita salida de clímax al confirmar rebote."""
    engine = ReboteEngine()
    
    # Serie de precios en caída hasta 0.1914 y última vela con pequeño rebote (0.1918)
    prices = [0.2000 - i * 0.003 for i in range(25)]
    prices[-1] = 0.1920 # Rebote alcista en el piso
    df_15m = create_bars(prices)
    df_5m = create_bars(prices[-10:])
    
    snap = {
        'lower_5': 0.1925,
        'lower_6': 0.1914,
        'upper_5': 0.2050,
        'upper_6': 0.2080
    }
    
    pos = {
        'id': 'pos-test-short',
        'symbol': 'ADAUSDT',
        'side': 'short',
        'entry_price': 0.1980,
        'size': 378.0
    }
    
    should_exit, reason, meta = engine.evaluate_climax_exit(
        symbol='ADAUSDT',
        direction='short',
        current_price=0.1918,
        df_15m=df_15m,
        df_5m=df_5m,
        position=pos,
        snap=snap
    )
    
    assert should_exit is True
    assert "SHORT_LOWER_REBOUND" in meta.get("climax_type", "")
    assert meta.get("pnl_pct", 0) > 2.0

def test_short_in_freefall_does_not_exit_early():
    """Valida que un SHORT en caída libre sin rebote mantenga la posición abierta (Runner)."""
    engine = ReboteEngine()
    
    # Serie de precios en caída sostenida a mitad de camino (0.1950 > LOWER_5)
    prices = [0.2000 - i * 0.002 for i in range(25)]
    df_15m = create_bars(prices)
    
    snap = {
        'lower_5': 0.1920,
        'lower_6': 0.1910,
    }
    
    pos = {
        'id': 'pos-test-short-run',
        'symbol': 'ADAUSDT',
        'side': 'short',
        'entry_price': 0.1980,
        'size': 378.0
    }
    
    should_exit, reason, meta = engine.evaluate_climax_exit(
        symbol='ADAUSDT',
        direction='short',
        current_price=0.1950,
        df_15m=df_15m,
        position=pos,
        snap=snap
    )
    
    assert should_exit is False

def test_long_rebote_climax_exit_at_upper_band():
    """Valida que un LONG en subida extrema hacia UPPER_5/6 emita salida al confirmar agotamiento."""
    engine = ReboteEngine()
    
    prices = [100.0 + i * 0.5 for i in range(25)]
    prices[-1] = 111.8 # Giro bajista tras tocar techo en 112.0
    df_15m = create_bars(prices)
    df_5m = create_bars(prices[-10:])
    
    snap = {
        'upper_5': 111.5,
        'upper_6': 113.0,
    }
    
    pos = {
        'id': 'pos-test-long',
        'symbol': 'SOLUSDT',
        'side': 'long',
        'entry_price': 102.0,
        'size': 10.0
    }
    
    should_exit, reason, meta = engine.evaluate_climax_exit(
        symbol='SOLUSDT',
        direction='long',
        current_price=111.8,
        df_15m=df_15m,
        df_5m=df_5m,
        position=pos,
        snap=snap
    )
    
    assert should_exit is True
    assert "LONG_UPPER_EXHAUSTION" in meta.get("climax_type", "")
    assert meta.get("pnl_pct", 0) > 8.0

def test_aduana_gatekeeper_approves_climax_rebote_exit():
    """Valida que ADUANA apruebe la orden de salida por clímax con prioridad sobre trailing."""
    gate = AduanaExitGatekeeper()
    
    req = ExitOrderRequest(
        position_id='pos-test-123',
        symbol='ADAUSDT',
        side='buy',
        order_type='MARKET',
        price=0.1918,
        volume=378.0,
        classification='ACTIVA',
        module_origin='CLIMAX_REBOTE_EXIT'
    )
    
    res = gate.arbitrate_and_register_order(req)
    assert res['approved'] is True
    assert res['action'] == 'PLACE'
