"""
Test Suite: Sistema de Pánico, Rescate EREP, Macro Extreme Gatekeeper y Escudo Anti-Racha
eTrade v5.0 / v6.0
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from app.strategy.panic_recovery_gate import (
    calculate_fibonacci_bands,
    check_candle_rejection,
    evaluate_panic_and_erep_status,
    evaluate_macro_extreme_entry
)
from app.strategy.position_guards import (
    can_open_position,
    register_sl_event,
    is_symbol_in_sl_cooldown,
    DAILY_SL_REGISTRY,
    SL_COOLDOWN_REGISTRY
)


def create_synthetic_df(prices, high_mult=1.002, low_mult=0.998):
    """Crea DataFrame de velas OHLC sintéticas para pruebas."""
    df = pd.DataFrame({
        'close': prices,
        'open': [p * 0.999 for p in prices],
        'high': [p * high_mult for p in prices],
        'low': [p * low_mult for p in prices],
    })
    return df


def test_calculate_fibonacci_bands():
    """Valida que las bandas de Fibonacci 1..6 y ATR se calculen correctamente."""
    prices = [100.0 + i * 0.1 for i in range(30)]
    df = create_synthetic_df(prices)
    bands = calculate_fibonacci_bands(df, current_price=103.0)

    assert bands['basis'] > 0
    assert bands['upper_6'] > bands['upper_5'] > bands['upper_1'] > bands['basis']
    assert bands['lower_6'] < bands['lower_5'] < bands['lower_1'] < bands['basis']
    assert bands['atr'] > 0


def test_micro_breakeven_exit():
    """Valida que una posición en pérdida que recupera a -$0.30 USD active MICRO_BREAKEVEN_EXIT."""
    pos = {
        'symbol': 'BTCUSDT',
        'side': 'short',
        'entry_price': 100.0,
        'unrealized_pnl': -0.30, # Recuperó a -$0.30 (dentro de breakeven/mínima pérdida)
        'total_investment': 50.0,
        'size': 1.0,
        'panic_active': True,    # Previamente entró en pánico / EREP y ahora recupera
    }
    df_15m = create_synthetic_df([100.0 + i * 0.05 for i in range(25)])
    eval_res = evaluate_panic_and_erep_status(pos, current_price=100.30, df_15m=df_15m)

    assert eval_res['should_exit'] is True
    assert eval_res['action'] == 'MICRO_BREAKEVEN_EXIT'
    assert 'PANIC_MICRO_BREAKEVEN_EXIT' in eval_res['rule_code']


def test_immunity_active_in_extreme_zone():
    """Valida que en UPPER_5/6 para SHORT, el Hard Cap del 5% queda suspendido (Inmunidad Activa)."""
    # Precio base 100
    prices = [100.0 for _ in range(25)]
    df_15m = create_synthetic_df(prices)
    bands = calculate_fibonacci_bands(df_15m, current_price=100.0)
    
    # Situamos el precio justo en UPPER_5
    px_u5 = bands['upper_5'] + 0.1
    pos = {
        'symbol': 'SOLUSDT',
        'side': 'short',
        'entry_price': 100.0,
        'unrealized_pnl': -3.50, # Drawdown de -7% sobre $50
        'total_investment': 50.0,
        'size': 2.0,
    }

    eval_res = evaluate_panic_and_erep_status(pos, current_price=px_u5, df_15m=df_15m)

    assert eval_res['in_extreme_zone'] is True
    assert eval_res['immunity_active'] is True
    assert eval_res['should_exit'] is False
    assert eval_res['action'] == 'WAIT_EREP_RECOVERY'
    assert eval_res['suggested_sl'] > px_u5 # NUNCA 0


def test_structural_breakout_exit():
    """Valida que si una vela de 15m cierra más allá de UPPER_6 con cuerpo lleno, corta por ruptura estructural."""
    prices = [100.0 for _ in range(25)]
    df_15m = create_synthetic_df(prices)
    bands = calculate_fibonacci_bands(df_15m, current_price=100.0)
    u6 = bands['upper_6']
    buf = bands['atr'] * 1.5

    # Vela 15m violenta cerrada muy por encima de UPPER_6
    breakout_px = u6 + buf + 1.0
    df_15m.loc[len(df_15m)] = {'open': u6, 'high': breakout_px + 0.5, 'low': u6 - 0.2, 'close': breakout_px}

    pos = {
        'symbol': 'SOLUSDT',
        'side': 'short',
        'entry_price': 100.0,
        'unrealized_pnl': -6.0,
        'total_investment': 50.0,
        'size': 2.0,
    }

    eval_res = evaluate_panic_and_erep_status(pos, current_price=breakout_px, df_15m=df_15m)

    assert eval_res['should_exit'] is True
    assert eval_res['action'] == 'STRUCTURAL_BREAKOUT_EXIT'
    assert 'STRUCTURAL_BREAKOUT_CUT' in eval_res['rule_code']


def test_hard_cap_5pct_in_intermediate_zone():
    """Valida que en zona intermedia, alcanzar 5% de pérdida del capital invertido corta incondicionalmente."""
    # Variación normal para que ATR y std sean realistas
    prices = [100.0 + (i % 5) * 0.4 for i in range(25)]
    df_15m = create_synthetic_df(prices)
    
    pos = {
        'symbol': 'BTCUSDT',
        'side': 'long',
        'entry_price': 100.0,
        'unrealized_pnl': -2.60, # Pérdida de $2.60 sobre $50 = 5.2% (>= 5%)
        'total_investment': 50.0,
        'size': 0.5,
    }

    # Precio en 98.0 (zona intermedia entre lower_2 y lower_4, lejos de lower_5)
    eval_res = evaluate_panic_and_erep_status(pos, current_price=98.0, df_15m=df_15m)

    assert eval_res['in_extreme_zone'] is False
    assert eval_res['should_exit'] is True
    assert eval_res['action'] == 'HARD_CAP_5PCT_EXIT'


def test_macro_extreme_gatekeeper_fresh_entry():
    """Valida que si precio toca UPPER_6 en 1H con mecha, genera orden MARKET nueva."""
    prices_1h = [100.0 for _ in range(25)]
    df_1h = create_synthetic_df(prices_1h)
    bands_1h = calculate_fibonacci_bands(df_1h, current_price=100.0)
    u6_1h = bands_1h['upper_6']

    # Vela de 5m con mecha superior marcada (rechazo del techo)
    df_5m = pd.DataFrame([
        {'open': u6_1h - 0.2, 'high': u6_1h + 0.5, 'low': u6_1h - 0.4, 'close': u6_1h - 0.3}
    ])

    res = evaluate_macro_extreme_entry(
        symbol='BTCUSDT',
        current_price=u6_1h,
        df_5m=df_5m,
        df_1h=df_1h,
        open_positions_for_symbol=[]
    )

    assert res['trigger'] is True
    assert res['action'] == 'ENTER_MACRO_CLIMAX'
    assert res['order_type'] == 'MARKET'
    assert res['side'] == 'short'
    assert res['score_bonus'] == 30


def test_macro_extreme_gatekeeper_scale_in_p2():
    """Valida que si ya hay una posición abierta en pérdida, ejecuta P2 Macro y recalcula P3 Breakeven."""
    prices_1h = [100.0 for _ in range(25)]
    df_1h = create_synthetic_df(prices_1h)
    bands_1h = calculate_fibonacci_bands(df_1h, current_price=100.0)
    u6_1h = bands_1h['upper_6']

    df_5m = pd.DataFrame([
        {'open': u6_1h - 0.2, 'high': u6_1h + 0.5, 'low': u6_1h - 0.4, 'close': u6_1h - 0.3}
    ])

    existing_p1 = {
        'symbol': 'BTCUSDT',
        'side': 'short',
        'entry_price': 100.0,
        'size': 1.0,
        'tranches_count': 1,
    }

    res = evaluate_macro_extreme_entry(
        symbol='BTCUSDT',
        current_price=u6_1h, # digamos 103.0
        df_5m=df_5m,
        df_1h=df_1h,
        open_positions_for_symbol=[existing_p1]
    )

    assert res['trigger'] is True
    assert res['action'] == 'SCALE_IN_P2_MACRO'
    assert res['order_type'] == 'MARKET'
    assert res['p2_qty'] == 1.0
    # P3 promedio ponderado entre 100.0 y u6_1h
    expected_p3 = (100.0 * 1.0 + u6_1h * 1.0) / 2.0
    assert abs(res['p3_weighted_breakeven'] - expected_p3) < 0.01


def test_shield_circuit_breaker_and_bypass():
    """Valida el Circuit Breaker diario (2 SLs por símbolo) y su bypass en oportunidades macro."""
    sym = 'SOLUSDT'
    now = datetime.now(timezone.utc)
    today = now.strftime('%Y-%m-%d')
    clean = sym.replace('/', '').upper()

    # Reset test registry
    DAILY_SL_REGISTRY.clear()
    SL_COOLDOWN_REGISTRY.clear()

    # Registramos 2 SLs en el día
    register_sl_event(sym, 'short', now)
    register_sl_event(sym, 'short', now)

    # Comprobamos que para una entrada normal se bloquea por Circuit Breaker
    check_normal = can_open_position(sym, 'short', is_macro_extreme=False)
    assert check_normal['allowed'] is False
    assert 'Circuit Breaker Diario activo' in check_normal['reason']

    # Comprobamos que si es una Oportunidad Macro Extrema (is_macro_extreme=True), se anula el bloqueo
    check_bypass = can_open_position(sym, 'short', is_macro_extreme=True)
    assert check_bypass['allowed'] is True
    assert 'Bypass de Zona Extrema Macro' in check_bypass['reason']
