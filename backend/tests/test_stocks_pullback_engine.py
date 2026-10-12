"""
Test Suite: PULLBACK BUYING ENGINE FOR STOCKS
=============================================
Pruebas exhaustivas para el motor de compras en retroceso:
- Macro 1H: EMA3 > EMA9 O EMA3 ascendente.
- Macro 15M: Bollinger Bands Expansion (Upper+, Lower-) con precio >= Basis.
- Filtros de Seguridad: Ventana Horaria 10:00 a 14:15 ET y Soporte VWAP.
- Disparadores Micro: Toque LOWER_5/6 con absorción y Órdenes LIMIT en EMA9/20 con Delta y TTL 5m.
- Ordenes LIMIT con soporte para ttl_minutes en stocks_order_executor.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.stocks.pullback_engine import (
    evaluate_macro_1h_condition,
    evaluate_macro_15m_bollinger_expansion,
    evaluate_macro_pullback_gate,
    is_in_pullback_time_window,
    check_vwap_support,
    calculate_adaptive_limit_prices,
    evaluate_lower5_6_absorption,
    evaluate_pullback_setup,
)


def _make_df(closes, opens=None, highs=None, lows=None, volumes=None):
    n = len(closes)
    if opens is None:
        opens = [c * 0.999 for c in closes]
    if highs is None:
        highs = [c * 1.002 for c in closes]
    if lows is None:
        lows = [c * 0.998 for c in closes]
    if volumes is None:
        volumes = [100000] * n
    return pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })


# ════════════════════════════════════════════════════════════════
# 1. PRUEBAS MACRO 1H
# ════════════════════════════════════════════════════════════════

def test_macro_1h_ema3_gt_ema9():
    """EMA3 > EMA9 en 1H debe calificar positivamente."""
    # Tendencia alcista clara
    closes = [10.0 + (i * 0.2) for i in range(20)]
    df_1h = _make_df(closes)
    res = evaluate_macro_1h_condition(df_1h)

    assert res['passed'] is True
    assert res['ema3_gt_ema9'] is True
    assert res['ema3'] > res['ema9']


def test_macro_1h_ema3_rising_even_if_below_ema9():
    """EMA3 ascendente califica incluso si todavía está cruzando por debajo de EMA9."""
    # Caída previa y fuerte rebote en las últimas velas
    closes = [20.0 - (i * 0.5) for i in range(15)] + [13.0, 13.5, 14.2]
    df_1h = _make_df(closes)
    res = evaluate_macro_1h_condition(df_1h)

    assert res['passed'] is True
    assert res['ema3_rising'] is True
    assert "ascendente" in res['reason'] or "EMA3 > EMA9" in res['reason']


def test_macro_1h_bearish_fails():
    """Si EMA3 < EMA9 y EMA3 sigue cayendo, debe fallar."""
    closes = [25.0 - (i * 0.3) for i in range(20)]
    df_1h = _make_df(closes)
    res = evaluate_macro_1h_condition(df_1h)

    assert res['passed'] is False
    assert res['ema3_gt_ema9'] is False
    assert res['ema3_rising'] is False


# ════════════════════════════════════════════════════════════════
# 2. PRUEBAS MACRO 15M (BOLLINGER EXPANSION)
# ════════════════════════════════════════════════════════════════

def test_macro_15m_bollinger_expansion_success():
    """Expansión de volatilidad con Upper subiendo, Lower bajando y Precio >= Basis."""
    # Simular expansión alcista de bandas
    base = 50.0
    closes = [base] * 20 + [51.0, 52.5, 54.0, 56.0]
    df_15m = _make_df(closes)
    res = evaluate_macro_15m_bollinger_expansion(df_15m, period=15)

    assert res['passed'] is True
    assert res['upper_slope'] > 0
    assert res['lower_slope'] < 0
    assert res['price_above_basis'] is True


def test_macro_15m_bollinger_expansion_below_basis_rejected():
    """Si hay expansión pero el precio está debajo de Basis (expansión bajista), debe rechazarse."""
    base = 50.0
    # Desplome abrupto que ensancha bandas hacia abajo
    closes = [base] * 20 + [48.0, 46.0, 44.0, 42.0]
    df_15m = _make_df(closes)
    res = evaluate_macro_15m_bollinger_expansion(df_15m, period=15)

    assert res['passed'] is False
    assert res['price_above_basis'] is False
    assert "bajo Basis" in res['reason']


def test_macro_gate_or_logic():
    """Si 1H pasa pero 15M no, la compuerta macro combinada debe pasar (lógica 'O')."""
    closes_1h_bull = [10.0 + (i * 0.2) for i in range(20)]
    df_1h = _make_df(closes_1h_bull)
    closes_15m_flat = [10.0] * 25
    df_15m = _make_df(closes_15m_flat)

    gate = evaluate_macro_pullback_gate(df_1h, df_15m)
    assert gate['macro_passed'] is True
    assert "1H:" in gate['summary_reason']


# ════════════════════════════════════════════════════════════════
# 3. FILTROS DE SEGURIDAD (HORARIO Y VWAP)
# ════════════════════════════════════════════════════════════════

def test_is_in_pullback_time_window():
    ny_tz = ZoneInfo('America/New_York')
    
    # 10:30 ET -> DENTRO
    dt_in = datetime(2026, 10, 12, 10, 30, tzinfo=ny_tz)
    assert is_in_pullback_time_window(dt_in) is True

    # 13:45 ET -> DENTRO
    dt_in_afternoon = datetime(2026, 10, 12, 13, 45, tzinfo=ny_tz)
    assert is_in_pullback_time_window(dt_in_afternoon) is True

    # 09:40 ET -> FUERA (muy temprano, horario de apertura volátil)
    dt_early = datetime(2026, 10, 12, 9, 40, tzinfo=ny_tz)
    assert is_in_pullback_time_window(dt_early) is False

    # 14:30 ET -> FUERA (muy tarde para esperar desarrollo del rebote)
    dt_late = datetime(2026, 10, 12, 14, 30, tzinfo=ny_tz)
    assert is_in_pullback_time_window(dt_late) is False


def test_check_vwap_support():
    vwap = 100.0
    # Sobre VWAP
    assert check_vwap_support(102.0, vwap) is True
    # Test justo de VWAP (0.5% margen)
    assert check_vwap_support(99.6, vwap) is True
    # Perforación clara bajo VWAP
    assert check_vwap_support(98.5, vwap) is False


# ════════════════════════════════════════════════════════════════
# 4. GATILLOS MICRO Y CÁLCULO DE ÓRDENES LIMIT CON DELTA
# ════════════════════════════════════════════════════════════════

def test_calculate_adaptive_limit_prices():
    current_price = 25.0
    ema9 = 24.80
    ema20 = 24.50
    spread = 0.04

    limits = calculate_adaptive_limit_prices(current_price, ema9, ema20, spread)
    delta = limits['delta']

    assert delta >= 0.01
    assert limits['limit_ema9'] == round(ema9 + delta, 2)
    assert limits['limit_ema20'] == round(ema20 + delta, 2)


def test_evaluate_lower5_6_absorption_trigger():
    """Toque de LOWER_5 con mecha de absorción en 5m debe gatillar la entrada."""
    bands = {'lower_5': 15.00, 'lower_6': 14.50}
    # Última vela hace mínimo en 14.95 (toca lower_5), abre en 15.20 y cierra en 15.25 (mecha inferior de 0.30)
    df_5m = pd.DataFrame({
        'open': [15.50, 15.20],
        'high': [15.55, 15.30],
        'low': [15.10, 14.95],
        'close': [15.15, 15.25],
        'volume': [50000, 120000]
    })

    res = evaluate_lower5_6_absorption(15.25, df_5m, bands)
    assert res['triggered'] is True
    assert res['level_name'] in ['LOWER_5', 'LOWER_6']
    assert "absorción" in res['reason']


def test_evaluate_lower5_6_no_absorption_rejected():
    """Toque de LOWER_5 pero cerrando en el mínimo absoluto (vela roja gigante, cuchillo cayendo)."""
    bands = {'lower_5': 15.00, 'lower_6': 14.50}
    df_5m = pd.DataFrame({
        'open': [15.50, 15.40],
        'high': [15.55, 15.40],
        'low': [15.20, 14.90],
        'close': [15.25, 14.92],  # Cerró casi en el mínimo absoluto, sin mecha
        'volume': [50000, 150000]
    })

    res = evaluate_lower5_6_absorption(14.92, df_5m, bands)
    assert res['triggered'] is False
    assert "sin absorción" in res['reason']


# ════════════════════════════════════════════════════════════════
# 5. PRUEBAS INTEGRADORAS (MASTER EVALUATOR)
# ════════════════════════════════════════════════════════════════

def test_evaluate_pullback_setup_master_market_on_lower():
    """Escenario completo: Ventana 11:00 ET, Macro 1H activa, Precio sobre VWAP, Toque LOWER_5 con absorción."""
    ny_tz = ZoneInfo('America/New_York')
    mock_now = datetime(2026, 10, 12, 11, 0, tzinfo=ny_tz)

    closes_1h = [10.0 + (i * 0.2) for i in range(20)]
    df_1h = _make_df(closes_1h)

    closes_15m = [13.5] * 25
    df_15m = _make_df(closes_15m)

    bands = {'lower_5': 13.00, 'lower_6': 12.60, 'upper_5': 14.50, 'upper_6': 15.00}
    df_5m = pd.DataFrame({
        'open': [13.40, 13.15],
        'high': [13.45, 13.25],
        'low': [13.10, 12.98],
        'close': [13.12, 13.22],
        'volume': [20000, 80000]
    })

    res = evaluate_pullback_setup(
        current_price=13.22,
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        bands_15m=bands,
        vwap=13.10,
        spread=0.02,
        now_dt=mock_now
    )

    assert res['pullback_triggered'] is True
    assert res['trigger_type'] == 'PULLBACK_LOWER_ABSORPTION'
    assert res['order_type'] == 'market'
    assert res['target_upper5'] == 14.50
    assert res['target_upper6'] == 15.00
    assert res['recommended_sl'] > 0


def test_evaluate_pullback_setup_master_limit_on_ema():
    """Escenario completo: Retesteo de EMA9 en 5m dispara órdenes LIMIT con delta y TTL 5m."""
    ny_tz = ZoneInfo('America/New_York')
    mock_now = datetime(2026, 10, 12, 11, 30, tzinfo=ny_tz)

    closes_1h = [20.0 + (i * 0.1) for i in range(20)]
    df_1h = _make_df(closes_1h)
    df_15m = _make_df([21.5] * 25)

    # 5m con 25 velas donde el precio actual está muy cerca de EMA9 (~21.80)
    closes_5m = [21.0 + (i * 0.04) for i in range(25)]
    curr_p = closes_5m[-1]
    df_5m = _make_df(closes_5m)

    bands = {'lower_5': 20.50, 'lower_6': 20.00, 'upper_5': 23.00, 'upper_6': 23.80}

    res = evaluate_pullback_setup(
        current_price=curr_p,
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        bands_15m=bands,
        vwap=21.20,
        spread=0.02,
        now_dt=mock_now
    )

    assert res['pullback_triggered'] is True
    assert res['trigger_type'] == 'PULLBACK_EMA_LIMIT'
    assert res['order_type'] == 'limit'
    assert len(res['limit_orders']) == 2
    assert res['limit_orders'][0]['ttl_minutes'] == 5
    assert res['limit_orders'][0]['limit_price'] > 0


def test_evaluate_pullback_setup_blocked_outside_hours():
    """Fuera de 10:00 - 14:15 ET se bloquea sin importar los indicadores."""
    ny_tz = ZoneInfo('America/New_York')
    mock_now = datetime(2026, 10, 12, 15, 0, tzinfo=ny_tz)  # 15:00 ET

    res = evaluate_pullback_setup(
        current_price=25.0,
        now_dt=mock_now
    )

    assert res['pullback_triggered'] is False
    assert "ventana operativa" in res['reason']
