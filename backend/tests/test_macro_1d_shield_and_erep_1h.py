"""
Test Suite: Escudo Macro 1D y Rescate EREP en Soportes/Resistencias 1H
Valida que:
1. Para LONG: un retroceso en 15m/1h con EMA3 < EMA9 no corte la posición si 1D es alcista (EMA3 >= EMA9 o ascendente).
2. Para SHORT: un rally en 15m/1h con EMA3 > EMA9 no corte la posición si 1D es bajista (EMA3 <= EMA9 o descendente).
3. Si 1D también confirma la pérdida de tendencia (colapso secular), el escape MTF sí se ejecute.
4. Al tocar la banda de Bollinger 1H (Lower para LONG o Upper para SHORT), EREP v2.0 active la compra/venta de rescate P2.
"""

import pytest
import pandas as pd
import numpy as np

from app.strategy.panic_recovery_gate import evaluate_panic_and_erep_status
from app.strategy.erep_recovery_engine import evaluate_erep_entry_trigger


def create_df(prices):
    return pd.DataFrame({
        'open': prices,
        'high': [p * 1.002 for p in prices],
        'low': [p * 0.998 for p in prices],
        'close': prices,
    })


def test_panic_gate_long_shielded_by_macro_1d():
    """
    LONG con retroceso intradía:
    15m y 1h tienen EMA3 < EMA9 (momentum en contra).
    Sin embargo, 1D tiene EMA3 ascendente (Macro alcista).
    El escape debe SUSPENDERSE por Escudo Macro 1D.
    """
    pos = {
        'symbol': 'ADAUSDT',
        'side': 'long',
        'entry_price': 0.2486,
        'unrealized_pnl': -0.78,
        'total_investment': 75.0,
        'size': 301.0,
    }
    current_price = 0.2460

    # 15m cayendo (EMA3 < EMA9)
    df_15m = create_df([0.2520 - i * 0.0005 for i in range(25)])
    # 1h cayendo (EMA3 < EMA9)
    df_1h = create_df([0.2540 - i * 0.0008 for i in range(25)])
    # 1D recuperando y subiendo (EMA3 ascendente)
    df_1d = create_df([0.2320, 0.2350, 0.2400, 0.2450, 0.2480, 0.2490])

    res = evaluate_panic_and_erep_status(
        position=pos,
        current_price=current_price,
        df_15m=df_15m,
        df_1h=df_1h,
        df_1d=df_1d
    )

    assert res['should_exit'] is False
    assert res['action'] == 'WAIT_MACRO_RECOVERY'
    assert res['immunity_active'] is True
    assert res['route_to_erep_1h'] is True
    assert res['rule_code'] == 'MACRO_1D_SHIELD_ACTIVE'
    assert 'Macro 1D' in res['reason']


def test_panic_gate_short_shielded_by_macro_1d():
    """
    SHORT con rebote intradía en contra:
    15m y 1h tienen EMA3 > EMA9 (momentum al alza en contra del short).
    Sin embargo, 1D tiene EMA3 descendente (Macro bajista).
    El escape debe SUSPENDERSE por Escudo Macro 1D.
    """
    pos = {
        'symbol': 'EURUSD',
        'side': 'short',
        'entry_price': 1.0900,
        'unrealized_pnl': -15.0, # 1.5% de pérdida sobre 1000 USD
        'total_investment': 1000.0,
        'size': 0.1,
    }
    current_price = 1.0915

    # 15m subiendo en contra (EMA3 > EMA9)
    df_15m = create_df([1.0880 + i * 0.0003 for i in range(25)])
    # 1h subiendo en contra (EMA3 > EMA9)
    df_1h = create_df([1.0870 + i * 0.0004 for i in range(25)])
    # 1D cayendo (EMA3 descendente)
    df_1d = create_df([1.1100, 1.1050, 1.1000, 1.0950, 1.0910, 1.0900])

    res = evaluate_panic_and_erep_status(
        position=pos,
        current_price=current_price,
        df_15m=df_15m,
        df_1h=df_1h,
        df_1d=df_1d
    )

    assert res['should_exit'] is False
    assert res['action'] == 'WAIT_MACRO_RECOVERY'
    assert res['immunity_active'] is True
    assert res['route_to_erep_1h'] is True
    assert res['rule_code'] == 'MACRO_1D_SHIELD_ACTIVE'
    assert 'Macro 1D' in res['reason']


def test_panic_gate_escapes_when_1d_macro_also_breaks():
    """
    Si 15m, 1h y 1D TODOS se voltean en contra (colapso macro general),
    el escape MTF sí debe actuar para proteger el capital.
    """
    pos = {
        'symbol': 'BTCUSDT',
        'side': 'long',
        'entry_price': 65000.0,
        'unrealized_pnl': -600.0, # 2.4% sobre 25000 USD
        'total_investment': 25000.0,
        'size': 0.1,
    }
    current_price = 63500.0

    # 15m cayendo
    df_15m = create_df([66000 - i * 100 for i in range(25)])
    # 1h cayendo
    df_1h = create_df([67000 - i * 150 for i in range(25)])
    # 1D también cayendo fuerte (EMA3 < EMA9 y cayendo)
    df_1d = create_df([70000, 68000, 66000, 64000, 63000])

    res = evaluate_panic_and_erep_status(
        position=pos,
        current_price=current_price,
        df_15m=df_15m,
        df_1h=df_1h,
        df_1d=df_1d
    )

    assert res['should_exit'] is True
    assert res['action'] == 'EMA_MTF_REVERSAL_ESCAPE'
    assert res['rule_code'] == 'EMA_MTF_REVERSAL_CUT'


def test_erep_p2_triggered_at_1h_bollinger_lower_long():
    """
    Valida que cuando un activo LONG toca la banda inferior de Bollinger en 1H,
    EREP v2.0 detecta la zona extrema y dispara execute_erep_p2.
    """
    pos = {
        'symbol': 'ADAUSDT',
        'side': 'long',
        'entry_price': 0.2486,
        'size': 301.0,
        'lots': 301.0,
    }
    current_price = 0.2444 # Suelo de 1H

    # Crear 1H donde 0.2444 esté en o debajo de la banda inferior
    prices_1h = [0.2490 for _ in range(25)]
    prices_1h[-1] = 0.2444
    df_1h = create_df(prices_1h)

    # 15m y 5m
    df_15m = create_df([0.2470 for _ in range(25)])
    df_5m = create_df([0.2445, 0.2444, 0.2446]) # Rebote micro 5m
    # 1D alcista
    df_1d = create_df([0.2350, 0.2400, 0.2480, 0.2490])

    trigger = evaluate_erep_entry_trigger(
        position=pos,
        df_5m=df_5m,
        df_15m=df_15m,
        current_price=current_price,
        market_type='crypto_futures',
        df_1h=df_1h,
        df_1d=df_1d
    )

    assert trigger is not None
    assert trigger['action'] == 'execute_erep_p2'
    assert trigger['side'] == 'long'
    assert 'LOWER_BB_1H' in trigger['target_band']
    assert trigger['p3_avg'] < pos['entry_price'] # Promedio P3 mejorado


def test_erep_p2_triggered_at_1h_bollinger_upper_short():
    """
    Valida que cuando un activo SHORT toca la banda superior de Bollinger en 1H,
    EREP v2.0 detecta la zona extrema y dispara execute_erep_p2.
    """
    pos = {
        'symbol': 'GBPUSD',
        'side': 'short',
        'entry_price': 1.3000,
        'lots': 0.10,
        'size': 0.10,
    }
    current_price = 1.3060 # Techo de 1H

    # Crear 1H donde 1.3060 esté en o sobre la banda superior
    prices_1h = [1.2980 for _ in range(25)]
    prices_1h[-1] = 1.3060
    df_1h = create_df(prices_1h)

    # 15m y 5m
    df_15m = create_df([1.3020 for _ in range(25)])
    df_5m = create_df([1.3058, 1.3060, 1.3059]) # Rechazo micro 5m
    # 1D bajista
    df_1d = create_df([1.3200, 1.3150, 1.3050, 1.2990])

    trigger = evaluate_erep_entry_trigger(
        position=pos,
        df_5m=df_5m,
        df_15m=df_15m,
        current_price=current_price,
        market_type='forex_futures',
        df_1h=df_1h,
        df_1d=df_1d
    )

    assert trigger is not None
    assert trigger['action'] == 'execute_erep_p2'
    assert trigger['side'] == 'short'
    assert 'UPPER_BB_1H' in trigger['target_band']
    assert trigger['p3_avg'] > pos['entry_price'] # Promedio P3 mejorado para SHORT


def test_panic_gate_long_shielded_by_macro_4h_alone():
    """
    LONG con retroceso intradía:
    15m y 1h tienen EMA3 < EMA9.
    1D no está disponible o neutral, pero 4H tiene EMA3 ascendente / sobre EMA20.
    El escape debe SUSPENDERSE por Escudo Macro 4H.
    """
    pos = {
        'symbol': 'SOLUSDT',
        'side': 'long',
        'entry_price': 150.0,
        'unrealized_pnl': -1.2,
        'total_investment': 100.0,
        'size': 1.0,
    }
    current_price = 148.0

    # 15m cayendo (EMA3 < EMA9)
    df_15m = create_df([152.0 - i * 0.2 for i in range(25)])
    # 1h cayendo (EMA3 < EMA9)
    df_1h = create_df([153.0 - i * 0.3 for i in range(25)])
    # 4H fuerte y ascendente (Macro alcista en 4H)
    df_4h = create_df([135.0, 140.0, 145.0, 148.0, 150.0])

    res = evaluate_panic_and_erep_status(
        position=pos,
        current_price=current_price,
        df_15m=df_15m,
        df_1h=df_1h,
        df_4h=df_4h
    )

    assert res['should_exit'] is False
    assert res['action'] == 'WAIT_MACRO_RECOVERY'
    assert res['immunity_active'] is True
    assert res['route_to_erep_1h'] is True
    assert res['rule_code'] == 'MACRO_4H_SHIELD_ACTIVE'
    assert '4H' in res['reason']


def test_panic_gate_short_shielded_by_macro_4h_alone():
    """
    SHORT con rebote intradía en contra:
    15m y 1h tienen EMA3 > EMA9.
    1D no está disponible, pero 4H tiene EMA3 descendente.
    El escape debe SUSPENDERSE por Escudo Macro 4H.
    """
    pos = {
        'symbol': 'USDJPY',
        'side': 'short',
        'entry_price': 155.00,
        'unrealized_pnl': -10.0,
        'total_investment': 1000.0,
        'size': 0.1,
    }
    current_price = 155.30

    # 15m subiendo en contra (EMA3 > EMA9)
    df_15m = create_df([154.50 + i * 0.05 for i in range(25)])
    # 1h subiendo en contra (EMA3 > EMA9)
    df_1h = create_df([154.30 + i * 0.06 for i in range(25)])
    # 4H cayendo (Macro bajista en 4H)
    df_4h = create_df([158.00, 157.00, 156.00, 155.50, 155.00])

    res = evaluate_panic_and_erep_status(
        position=pos,
        current_price=current_price,
        df_15m=df_15m,
        df_1h=df_1h,
        df_4h=df_4h
    )

    assert res['should_exit'] is False
    assert res['action'] == 'WAIT_MACRO_RECOVERY'
    assert res['immunity_active'] is True
    assert res['route_to_erep_1h'] is True
    assert res['rule_code'] == 'MACRO_4H_SHIELD_ACTIVE'
    assert '4H' in res['reason']
