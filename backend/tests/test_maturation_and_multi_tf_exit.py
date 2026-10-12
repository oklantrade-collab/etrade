"""
Test Suite: Motor de Maduración y Salidas Multi-Timeframe en Stocks (eTrade v6.0)
================================================================================
Verifica:
1. Piso de Maduración (>= +1.5%): Micro-ruido en 5m no cierra trades prematuros si 15m está viva.
2. Falso Agotamiento en Zona 1 (Basis a Upper_1): Prohibido salir en cuna del movimiento.
3. Agotamiento Estructural en Zona 2: Salida monetizada cuando 15m EMA agota y ganancia >= 1.5%.
4. Simetría Inversa para SHORTs: EMA3 < EMA9 mantiene y EMA3 >= EMA9 sale.
5. Cutoff Horario Intradía 15:15 ET: Bloqueo de nuevas compras HOT en las últimas 3 velas.
6. EOD Kinetic Trailing (15:15 a 15:50 ET): Cabalga tendencia viva protegiendo 70% de pico.
7. Cierre Total Inmediato EOD ante quiebre de 15m EMA tras 15:15 ET.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.stocks.aduana_stocks_exit_engine import (
    calculate_fibonacci_sub_bands,
    evaluate_15m_ema_structure,
    is_eod_final_candles,
    evaluate_aduana_stocks_exit
)
from app.strategy.panic_recovery_gate import calculate_fibonacci_bands
from app.stocks.stocks_order_executor import execute_market_order, place_limit_order, _is_after_1515_et


def make_df(prices, volumes=None, high_mult=1.001, low_mult=0.998, open_mult=0.999):
    """Genera DataFrame de velas OHLCV consistente para pruebas."""
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


def test_early_5m_pullback_does_not_close_before_maturation():
    """
    Test 1: Posición con +0.4% de ganancia y EMA3_15m > EMA9_15m.
    Ocurre micro-retroceso en 5m (Close < EMA3_5m, EMA3 < EMA9).
    Valida que el piso de maduración (<+1.5%) bloquee el cierre y retorne HOLD con Breakeven.
    """
    # 25 velas 15m en tendencia alcista sana
    prices_15m = [100.0 + i * 0.25 for i in range(25)] # De 100.0 a 106.0
    df_15m = make_df(prices_15m)

    # 10 velas 5m con micro-retroceso final
    prices_5m = [100.8, 100.75, 100.7, 100.65, 100.6, 100.5, 100.45, 100.42, 100.40, 100.38]
    df_5m = make_df(prices_5m)

    pos = {
        'symbol': 'INTR',
        'side': 'long',
        'entry_price': 100.0,
        'shares': 10,
    }
    cur_p = 100.40 # +0.4% de ganancia (situación de INTR / RXRX)

    res = evaluate_aduana_stocks_exit(pos, current_price=cur_p, df_5m=df_5m, df_15m=df_15m)
    assert res['should_close'] is False
    assert res['action'] == 'HOLD'
    assert 'Fase de Maduración' in res['reason']
    assert res['gain_pct'] == 0.4


def test_exhaustion_in_zone_1_ignored_while_15m_ema_bullish():
    """
    Test 2: Posición entre Basis y Upper_1 (Zona 1) con +0.3% de ganancia.
    Valida que in_exhaustion_zone sea False en Zona 1 y que el motor NO liquide
    la posición prematuramente por falso agotamiento.
    """
    prices_15m = [50.0 + i * 0.1 for i in range(25)]
    df_15m = make_df(prices_15m)
    bands = calculate_fibonacci_bands(df_15m, current_price=51.5)

    basis = bands['basis']
    u1 = bands['upper_1']
    span = u1 - basis
    # Ubicar precio en el tercio superior de Zona 1
    p_zone1_high = basis + (span * 0.85)

    sub_res = calculate_fibonacci_sub_bands(p_zone1_high, bands, side='long')
    assert sub_res['zone'] == 1
    # En Zona 1 NUNCA debe marcar agotamiento
    assert sub_res['in_exhaustion_zone'] is False

    pos = {
        'symbol': 'SBS',
        'side': 'long',
        'entry_price': basis,
        'shares': 20,
    }
    prices_5m = [p_zone1_high + 0.1, p_zone1_high, p_zone1_high - 0.05, p_zone1_high - 0.1]
    df_5m = make_df(prices_5m)

    res = evaluate_aduana_stocks_exit(pos, current_price=p_zone1_high, df_5m=df_5m, df_15m=df_15m)
    assert res['should_close'] is False
    assert res['action'] == 'HOLD'


def test_exhaustion_in_zone_2_with_15m_ema_cross_triggers_exit():
    """
    Test 3: Posición en Zona 2 (Upper_1 a Upper_3) con ganancia madura (+2.5% >= 1.5%).
    La estructura de 15m muestra quiebre/agotamiento (EMA3 <= EMA9) y 5m confirma debilidad.
    Valida salida monetizada total.
    """
    # 25 velas 15m con curva descendente al final (EMA3 <= EMA9)
    prices_15m = [100.0 + i * 0.2 for i in range(20)] + [104.0, 103.5, 103.0, 102.6, 102.5]
    df_15m = make_df(prices_15m)
    bands = calculate_fibonacci_bands(df_15m, current_price=102.5)

    ema_struct = evaluate_15m_ema_structure(df_15m, side='long')
    assert ema_struct['is_exhausted'] is True

    # Micro 5m con cruce bajista
    prices_5m = [103.8, 103.6, 103.5, 103.4, 103.2, 103.0, 102.8, 102.6, 102.5, 102.4]
    df_5m = make_df(prices_5m)

    pos = {
        'symbol': 'NVDA',
        'side': 'long',
        'entry_price': 100.0,
        'shares': 5,
    }

    res = evaluate_aduana_stocks_exit(pos, current_price=102.5, df_5m=df_5m, df_15m=df_15m)
    assert res['should_close'] is True
    assert res['action'] == 'CLOSE_TOTAL'
    assert res['pct_to_close'] == 100
    assert res['gain_pct'] == 2.5
    assert 'ADUANA_STK_EXHAUSTION_EXIT' in res['rule_code']


def test_short_position_15m_ema_behavior():
    """
    Test 4: Simetría inversa para posiciones SHORT.
    A) SHORT en ganancia incipiente (+0.8%), EMA3_15m < EMA9_15m viva. Micro rebote 5m no cierra.
    B) SHORT con +2.5% de ganancia, quiebre alcista EMA3_15m >= EMA9_15m activa salida con ganancia.
    """
    # A) SHORT VIVO: precio cayendo
    prices_short_alive = [100.0 - i * 0.3 for i in range(25)] # De 100 a 92.8
    df_15m_alive = make_df(prices_short_alive)
    ema_alive = evaluate_15m_ema_structure(df_15m_alive, side='short')
    assert ema_alive['is_trend_alive'] is True
    assert ema_alive['is_exhausted'] is False

    pos_short = {
        'symbol': 'SQQQ',
        'side': 'short',
        'entry_price': 100.0,
        'shares': 10,
    }
    # Micro rebote 5m menor (aún en favor de SHORT)
    prices_5m = [99.5, 99.4, 99.3, 99.2, 99.1, 99.0, 99.05, 99.1, 99.15, 99.2]
    df_5m = make_df(prices_5m)
    res_alive = evaluate_aduana_stocks_exit(pos_short, current_price=99.2, df_5m=df_5m, df_15m=df_15m_alive)
    assert res_alive['should_close'] is False
    assert res_alive['action'] == 'HOLD'

    # B) SHORT AGOTADO: rebote fuerte en 15m
    prices_short_exhausted = [100.0 - i * 0.3 for i in range(20)] + [94.0, 95.0, 96.0, 97.0, 97.5]
    df_15m_exh = make_df(prices_short_exhausted)
    ema_exh = evaluate_15m_ema_structure(df_15m_exh, side='short')
    assert ema_exh['is_exhausted'] is True

    # 10 velas de 5m con giro alcista claro (EMA3 > EMA9)
    prices_5m_up = [94.0, 94.5, 95.0, 95.5, 96.0, 96.5, 96.8, 97.0, 97.2, 97.5]
    df_5m_up = make_df(prices_5m_up)
    res_exh = evaluate_aduana_stocks_exit(pos_short, current_price=97.5, df_5m=df_5m_up, df_15m=df_15m_exh)
    assert res_exh['should_close'] is True
    assert res_exh['action'] == 'CLOSE_TOTAL'
    assert res_exh['gain_pct'] == 2.5 # Ganó de 100.0 a 97.5


def test_cutoff_time_blocks_hot_entry_after_1515_et():
    """
    Test 5: Cutoff Horario Intradía 15:15 ET (últimas 3 velas de mercado).
    Valida que a las 15:20 ET o 15:35 ET se rechace cualquier compra HOT,
    mientras que a las 14:00 ET se permita.
    """
    tz_ny = ZoneInfo('America/New_York')
    dt_after = datetime(2026, 10, 7, 15, 35, tzinfo=tz_ny)
    dt_before = datetime(2026, 10, 7, 14, 0, tzinfo=tz_ny)

    assert _is_after_1515_et(dt_after) is True
    assert _is_after_1515_et(dt_before) is False

    rule_hot = {'group_name': 'HOT_VOLUME', 'limit_trigger_pct': 0.005}
    ctx_after = {'price': 50.0, 'now_dt': dt_after}

    res_market = execute_market_order('INTR', 'buy', 'Aa30_STK', ctx_after, rule_hot)
    assert res_market['success'] is False
    assert 'Cutoff 15:15 ET' in res_market['reason']

    ctx_lmt = {'price': 50.0, 'smart_limit_price': 49.8, 'now_dt': dt_after}
    res_limit = place_limit_order('INTR', 'buy', 'HOT_BUY_LMT', ctx_lmt, rule_hot)
    assert res_limit['success'] is False
    assert 'Cutoff 15:15 ET' in res_limit['reason']


def test_eod_trailing_tightened_in_last_3_candles():
    """
    Test 6: Régimen EOD (15:15 a 15:50 ET) con Trailing Stop Acelerado.
    Si la tendencia de 15m está viva, cabalga pero protegiendo piso del 70% de ganancia máxima.
    Si perfora el piso de 70%, ejecuta cierre protector.
    """
    tz_ny = ZoneInfo('America/New_York')
    dt_eod = datetime(2026, 10, 7, 15, 30, tzinfo=tz_ny)
    assert is_eod_final_candles(dt_eod) is True

    # 15m alcista fuerte viva
    prices_15m = [100.0 + i * 0.2 for i in range(25)]
    df_15m = make_df(prices_15m)

    pos = {
        'symbol': 'TSLA',
        'side': 'long',
        'entry_price': 100.0,
        'shares': 10,
        'highest_price_reached': 104.0, # Pico +4.0%
    }

    # A) Precio en 103.5 (+3.5% de ganancia, conserva > 70% del pico de +4.0% que es +2.8%)
    # 5m sin perforar
    prices_5m_ok = [103.2, 103.3, 103.4, 103.5]
    df_5m_ok = make_df(prices_5m_ok)
    res_hold = evaluate_aduana_stocks_exit(
        pos, current_price=103.5, df_5m=df_5m_ok, df_15m=df_15m, now_dt=dt_eod
    )
    assert res_hold['should_close'] is False
    assert res_hold['action'] == 'HOLD'
    assert 'EOD Trailing Activo' in res_hold['reason']

    # B) Precio retrocede a 102.5 (+2.5% de ganancia, menor al 70% del pico de 4.0% -> 2.8%)
    res_floor_break = evaluate_aduana_stocks_exit(
        pos, current_price=102.5, df_5m=df_5m_ok, df_15m=df_15m, now_dt=dt_eod
    )
    assert res_floor_break['should_close'] is True
    assert res_floor_break['action'] == 'CLOSE_TOTAL'
    assert 'ADUANA_STK_EOD_TRAILING_FLOOR_BREAK' in res_floor_break['rule_code']


def test_eod_immediate_close_if_15m_ema_breaks_after_1515():
    """
    Test 7: A las 15:25 ET (últimas 3 velas), EMA3_15m cruza por debajo de EMA9_15m.
    No esperar al cierre a mercado de 15:50 ET: se ejecuta cierre total inmediato.
    """
    tz_ny = ZoneInfo('America/New_York')
    dt_eod = datetime(2026, 10, 7, 15, 25, tzinfo=tz_ny)

    # 15m con quiebre bajista (EMA3 <= EMA9)
    prices_15m = [100.0 + i * 0.2 for i in range(20)] + [104.0, 103.5, 102.8, 102.2, 102.0]
    df_15m = make_df(prices_15m)

    pos = {
        'symbol': 'AMD',
        'side': 'long',
        'entry_price': 100.0,
        'shares': 8,
    }

    res = evaluate_aduana_stocks_exit(
        pos, current_price=102.0, df_5m=None, df_15m=df_15m, now_dt=dt_eod
    )
    assert res['should_close'] is True
    assert res['action'] == 'CLOSE_TOTAL'
    assert res['gain_pct'] == 2.0
    assert 'ADUANA_STK_EOD_15M_BREAK' in res['rule_code']
