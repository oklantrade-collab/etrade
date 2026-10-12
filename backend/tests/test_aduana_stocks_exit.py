"""
Test Suite: ADUANA Stocks Exit Engine & Saneamiento de Salidas en Stocks
eTrade v6.0
"""

import pytest
import pandas as pd
import numpy as np

from app.strategy.panic_recovery_gate import calculate_fibonacci_bands
from app.stocks.aduana_stocks_exit_engine import (
    calculate_fibonacci_sub_bands,
    evaluate_fuel_15m,
    evaluate_5m_micro_trigger,
    evaluate_macro_bollinger_levels,
    evaluate_accelerated_trailing_stop,
    evaluate_aduana_stocks_exit
)


def create_ohlc_df(prices, volumes=None, high_mult=1.0005, low_mult=0.997, open_mult=0.998):
    """Crea DataFrame de velas OHLCV para pruebas."""
    n = len(prices)
    if volumes is None:
        volumes = [100000.0] * n
    return pd.DataFrame({
        'open': [p * open_mult for p in prices],
        'high': [p * high_mult for p in prices],
        'low': [p * low_mult for p in prices],
        'close': prices,
        'volume': volumes
    })


def test_fibonacci_sub_bands_division():
    """Valida la división de bandas de Fibonacci en 3 sub-bandas y detección de agotamiento."""
    prices = [100.0 for _ in range(25)]
    df_15m = create_ohlc_df(prices)
    bands = calculate_fibonacci_bands(df_15m, current_price=100.0)

    u1 = bands['upper_1']
    u2 = bands['upper_2']
    span = u2 - u1

    # Precio en Sub-Banda 1 (primer tercio)
    p_sub1 = u1 + (span * 0.15)
    res_sub1 = calculate_fibonacci_sub_bands(p_sub1, bands, side='long')
    assert res_sub1['sub_band'] == 1
    assert res_sub1['in_exhaustion_zone'] is False

    # Precio en Sub-Banda 3 (tercer tercio -> agotamiento)
    p_sub3 = u1 + (span * 0.85)
    res_sub3 = calculate_fibonacci_sub_bands(p_sub3, bands, side='long')
    assert res_sub3['sub_band'] == 3
    assert res_sub3['in_exhaustion_zone'] is True


def test_fuel_15m_high_guards_room():
    """Valida que combustible ALTO en 15m (RVOL > 1.2, vela verde) guarda espacio y bloquea salidas por impulso."""
    prices = [100.0 + i * 0.2 for i in range(25)]
    # Volumen promedio 100k, última vela con 200k (RVOL = 2.0x) y vela verde expansiva
    vols = [100000.0] * 24 + [200000.0]
    df_15m = create_ohlc_df(prices, volumes=vols, high_mult=1.0005, low_mult=0.997, open_mult=0.998)

    fuel = evaluate_fuel_15m(df_15m, side='long')
    assert fuel['state'] == 'HIGH_FUEL'
    assert fuel['keep_room'] is True

    # Evaluamos en la función maestra con posición en ganancia
    pos = {
        'symbol': 'AAPL',
        'side': 'long',
        'entry_price': 100.0,
        'shares': 10,
    }
    # Micro 5m con EMA3 < EMA9 (ruido menor de 5m)
    prices_5m = [104.0, 104.2, 104.1, 103.9, 103.8]
    df_5m = create_ohlc_df(prices_5m)

    res = evaluate_aduana_stocks_exit(pos, current_price=104.8, df_5m=df_5m, df_15m=df_15m)
    # Debe guardar espacio y NO cerrar por impulso menor
    assert res['should_close'] is False
    assert res['action'] == 'HOLD'
    assert 'Guardando espacio' in res['reason']


def test_fuel_exhausted_and_sub_band_3_triggers_exit():
    """Valida que si combustible se agota y precio está en Sub-Banda 3 con giro 5m, ejecuta salida con ganancia."""
    prices = [100.0 + i * 0.1 for i in range(25)]
    # Volumen secándose (50k vs promedio 100k -> RVOL = 0.5x)
    vols = [100000.0] * 24 + [45000.0]
    df_15m = create_ohlc_df(prices, volumes=vols)
    bands = calculate_fibonacci_bands(df_15m, current_price=102.5)

    u2 = bands['upper_2']
    u3 = bands['upper_3']
    target_px = u2 + (u3 - u2) * 0.85 # Sub-Banda 3

    # Velas de 5m con cruce EMA3 < EMA9 y Bollinger horizontal
    prices_5m = [103.0, 103.2, 103.1, 102.9, 102.8, 102.7, 102.6, 102.5, 102.4, 102.3]
    df_5m = create_ohlc_df(prices_5m)

    pos = {
        'symbol': 'SATL',
        'side': 'long',
        'entry_price': 100.0,
        'shares': 5,
    }

    res = evaluate_aduana_stocks_exit(pos, current_price=target_px, df_5m=df_5m, df_15m=df_15m)
    assert res['should_close'] is True
    assert res['action'] == 'CLOSE_TOTAL'
    assert res['pct_to_close'] == 100
    assert 'ADUANA_STK_EXHAUSTION_EXIT' in res['rule_code']


def test_zero_dollar_threshold_locks_gain():
    """Valida que una ganancia pequeña de centavos (< $1.00 USD) SÍ se ejecuta y nunca se bloquea."""
    # 5 acciones compradas a $6.00 ($30.00 inversión). Precio sube a $6.15 (+2.5% = +$0.75 USD < $1.00 USD)
    pos = {
        'symbol': 'SATL',
        'side': 'long',
        'entry_price': 6.00,
        'shares': 5,
    }
    # 25 velas con rango moderado para ubicar 6.15 en sub-banda normal y no en UPPER_6
    prices_15m = [6.00 + i * 0.01 for i in range(25)]
    vols = [10000.0] * 24 + [4000.0] # Combustible bajo (RVOL = 0.4x)
    df_15m = create_ohlc_df(prices_15m, volumes=vols)

    # 5m con debilidad EMA3 < EMA9
    prices_5m = [6.18, 6.17, 6.16, 6.15, 6.14, 6.13, 6.12, 6.11, 6.10, 6.09]
    df_5m = create_ohlc_df(prices_5m)

    res = evaluate_aduana_stocks_exit(pos, current_price=6.15, df_5m=df_5m, df_15m=df_15m)
    assert res['should_close'] is True
    assert res['pnl_usd'] == 0.75
    assert res['gain_pct'] == 2.5
    # Jamás debe retornar action == HOLD por culpa de $0.75 < $1.00 USD
    assert res['action'] == 'CLOSE_TOTAL'


def test_macro_bb_1h_partial_50_tp():
    """Valida que al tocar Banda Bollinger Superior en 1H con agotamiento en 5m, toma 50% de ganancia parcial."""
    prices_1h = [100.0 for _ in range(25)]
    df_1h = create_ohlc_df(prices_1h)
    bb_upper_1h = 100.0 + (2.0 * 100.0 * 0.002) # ~100.40

    prices_5m = [100.5, 100.45, 100.4, 100.35, 100.3, 100.25, 100.2, 100.15, 100.1, 100.05]
    df_5m = create_ohlc_df(prices_5m)
    df_15m = create_ohlc_df([100.0 for _ in range(25)])

    pos = {
        'symbol': 'SOFI',
        'side': 'long',
        'entry_price': 98.0,
        'shares': 10,
    }

    res = evaluate_aduana_stocks_exit(
        pos, current_price=bb_upper_1h,
        df_5m=df_5m, df_15m=df_15m, df_1h=df_1h
    )

    assert res['should_close'] is True
    assert res['action'] == 'CLOSE_PARTIAL_50'
    assert res['pct_to_close'] == 50
    assert res['shares_to_close'] == 5
    assert 'ADUANA_STK_MACRO_1H_TP50' in res['rule_code']


def test_macro_bb_4h_and_1d_major_tp():
    """Valida que al tocar Banda Bollinger Superior en 4H o 1D, ejecuta cierre mayoritario (75% o 100%)."""
    prices_4h = [50.0 for _ in range(25)]
    df_4h = create_ohlc_df(prices_4h)
    bb_upper_4h = 50.0 + (2.0 * 50.0 * 0.002)

    prices_5m = [50.5, 50.4, 50.3, 50.2, 50.1, 50.0, 49.9, 49.8, 49.7, 49.6]
    df_5m = create_ohlc_df(prices_5m)
    df_15m = create_ohlc_df([50.0 for _ in range(25)])

    pos = {
        'symbol': 'FSLY',
        'side': 'long',
        'entry_price': 45.0,
        'shares': 8,
    }

    res = evaluate_aduana_stocks_exit(
        pos, current_price=bb_upper_4h,
        df_5m=df_5m, df_15m=df_15m, df_4h=df_4h
    )

    assert res['should_close'] is True
    assert res['action'] in ('CLOSE_MAJOR_75', 'CLOSE_TOTAL')
    assert res['pct_to_close'] == 75
    assert res['shares_to_close'] == 6
    assert 'ADUANA_STK_MACRO_4H_TP' in res['rule_code']


def test_accelerated_trailing_stop_in_upper_6():
    """Valida el Trailing Stop Acelerado en UPPER_6: toma parcial del 50% y trailing vela a vela en 5m."""
    prices_15m = [100.0 for _ in range(25)]
    df_15m = create_ohlc_df(prices_15m)
    bands = calculate_fibonacci_bands(df_15m, current_price=100.0)
    u6 = bands['upper_6']

    pos = {
        'symbol': 'NVDA',
        'side': 'long',
        'entry_price': 90.0,
        'shares': 10,
        'tp_block1_executed': False,
    }

    # 1. Primer toque de UPPER_6 -> Toma 50% al clímax
    res_climax = evaluate_accelerated_trailing_stop(pos, current_price=u6, df_5m=None, bands_15m=bands)
    assert res_climax['action'] == 'TAKE_PROFIT_50_CLIMAX'
    assert res_climax['pct'] == 50
    assert 'ADUANA_STK_CLIMAX_UPPER6_TP50' in res_climax['rule_code']

    # 2. Segunda fase con 50% ya tomado: el precio cae por debajo del Low de la vela previa de 5m
    pos['tp_block1_executed'] = True
    df_5m = pd.DataFrame([
        {'open': u6, 'high': u6 + 0.5, 'low': u6 - 0.2, 'close': u6 + 0.3}, # Low_prev = u6 - 0.2
        {'open': u6 + 0.3, 'high': u6 + 0.3, 'low': u6 - 0.5, 'close': u6 - 0.4}
    ])
    # Precio actual perfora Low_prev
    res_trail = evaluate_accelerated_trailing_stop(pos, current_price=u6 - 0.3, df_5m=df_5m, bands_15m=bands)
    assert res_trail['action'] == 'CLOSE_TRAILING_LOW_BREAK'
    assert res_trail['pct'] == 100
    assert 'ADUANA_STK_KINETIK_LOW_BREAK' in res_trail['rule_code']
