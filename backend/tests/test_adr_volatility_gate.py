"""
Test Suite: ADR & Volatility Fuel Gate (Stocks)
eTrade v6.0
"""

import pytest
import pandas as pd
import numpy as np

from app.stocks.adr_volatility_gate import (
    calculate_adr,
    calculate_bollinger_bandwidth_15m,
    evaluate_adr_and_volatility_gate
)
from app.stocks.stocks_rule_engine import StocksRuleEngine


def create_daily_df(ranges_pct, base_price=10.0):
    """Crea DataFrame de velas diarias con un rango porcentual específico."""
    n = len(ranges_pct)
    closes = [base_price * (1.0 + (i * 0.005)) for i in range(n)]
    highs = []
    lows = []
    for c, r_pct in zip(closes, ranges_pct):
        r_usd = c * (r_pct / 100.0)
        highs.append(c + (r_usd * 0.6))
        lows.append(c - (r_usd * 0.4))

    return pd.DataFrame({
        'open': [c * 0.998 for c in closes],
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': [1_000_000.0] * n
    })


def create_15m_df(prices, bandwidth_mult=0.03, volumes=None):
    """Crea DataFrame de 15m con bandas y volumen configurables."""
    n = len(prices)
    if volumes is None:
        volumes = [20_000.0] * n

    highs = [p * (1.0 + (bandwidth_mult * 0.5)) for p in prices]
    lows = [p * (1.0 - (bandwidth_mult * 0.5)) for p in prices]

    return pd.DataFrame({
        'open': [p * 0.999 for p in prices],
        'high': highs,
        'low': lows,
        'close': prices,
        'volume': volumes
    })


def test_adr_calculation_accuracy():
    """Valida el cálculo matemático exacto de ADR a 14 velas y consumo del rango actual."""
    # 14 días con exactamente 5.0% de rango, y hoy con 2.5% recorrido (50% consumido)
    ranges_14 = [5.0] * 14 + [2.5]
    df_1d = create_daily_df(ranges_14, base_price=100.0)

    res = calculate_adr(df_1d, period=14)
    assert abs(res['adr_pct'] - 5.0) < 0.1
    assert abs(res['today_range_pct'] - 2.5) < 0.1
    assert abs(res['consumed_pct'] - 50.0) < 3.0
    assert res['has_room'] is True


def test_low_adr_stock_rejected_in_hot_rules():
    """Valida que un activo aletargado tipo SBS (ADR = 2.45%) sea RECHAZADO en compras HOT."""
    ranges_sbs = [2.45] * 14 + [1.50]
    df_1d = create_daily_df(ranges_sbs, base_price=6.38)
    df_15m = create_15m_df([6.38] * 25, bandwidth_mult=0.03, volumes=[20_000.0] * 25)

    res = evaluate_adr_and_volatility_gate(
        df_1d=df_1d,
        df_15m=df_15m,
        current_price=6.38,
        rule_code='HOT_BB_PULLBACK_5M',
        group_name='inversiones_hot'
    )

    assert res['passed'] is False
    assert any("ADR 14D insuficiente" in f for f in res['failures'])


def test_high_adr_stock_accepted_with_fuel():
    """Valida que un activo volátil tipo RXRX o SMCI (ADR >= 5.0%) con espacio sea ACEPTADO."""
    ranges_rxrx = [7.50] * 14 + [3.00] # Consumido < 50%
    df_1d = create_daily_df(ranges_rxrx, base_price=20.0)
    # 15m con volumen saludable de 35,000 acciones y expansión
    vols = [20_000.0] * 24 + [35_000.0]
    prices = [20.0 + i * 0.05 for i in range(25)]
    df_15m = create_15m_df(prices, bandwidth_mult=0.04, volumes=vols)

    res = evaluate_adr_and_volatility_gate(
        df_1d=df_1d,
        df_15m=df_15m,
        current_price=21.2,
        rule_code='HOT_BB_PULLBACK_5M',
        group_name='inversiones_hot'
    )

    assert res['passed'] is True
    assert len(res['failures']) == 0
    assert res['breakout_prob'] >= 65


def test_exhausted_adr_rejected_without_climax_volume():
    """Valida que si ya consumió >= 80% de su ADR sin RVOL clímax (>= 2.0x), se bloquee la entrada."""
    # ADR = 5.0%, pero hoy ya se movió 4.6% (92% consumido)
    ranges_exhausted = [5.0] * 14 + [4.6]
    df_1d = create_daily_df(ranges_exhausted, base_price=50.0)
    # Volumen normal (RVOL 1.1x)
    vols = [20_000.0] * 24 + [22_000.0]
    df_15m = create_15m_df([50.0] * 25, bandwidth_mult=0.03, volumes=vols)

    res = evaluate_adr_and_volatility_gate(
        df_1d=df_1d,
        df_15m=df_15m,
        current_price=50.0,
        rule_code='HOT_DIP_BUY',
        group_name='hot_by_volume'
    )

    assert res['passed'] is False
    assert any("Rango diario agotado" in f for f in res['failures'])


def test_dead_bollinger_compression_rejected():
    """Valida que una compresión muerta de Bollinger (Bandwidth < 2.0% plano como SBS) sea bloqueada."""
    # ADR adecuado pero bandas de 15m aplastadas en 1.1%
    ranges_1d = [4.5] * 14 + [1.5]
    df_1d = create_daily_df(ranges_1d, base_price=10.0)
    # Bandas con bandwidth de apenas 1.0% (0.010 mult) y precio estancado
    df_15m = create_15m_df([10.0] * 25, bandwidth_mult=0.010, volumes=[20_000.0] * 25)

    res = evaluate_adr_and_volatility_gate(
        df_1d=df_1d,
        df_15m=df_15m,
        current_price=10.0,
        rule_code='HOT_BB_PULLBACK_5M',
        group_name='inversiones_hot',
        rvol_15m_override=1.0
    )

    assert res['passed'] is False
    assert any("Compresión muerta en 15m" in f for f in res['failures'])


def test_ghost_candle_volume_rejected():
    """Valida que una vela de 134 acciones (como la de SBS) sea bloqueada por falta de liquidez."""
    ranges_1d = [5.0] * 14 + [1.5]
    df_1d = create_daily_df(ranges_1d, base_price=10.0)
    # Vela actual con solo 134 acciones
    vols = [10_000.0] * 24 + [134.0]
    df_15m = create_15m_df([10.0] * 25, bandwidth_mult=0.03, volumes=vols)

    res = evaluate_adr_and_volatility_gate(
        df_1d=df_1d,
        df_15m=df_15m,
        current_price=10.0,
        rule_code='HOT_BB_PULLBACK_5M',
        group_name='inversiones_hot'
    )

    assert res['passed'] is False
    assert any("Vela anémica" in f for f in res['failures'])


def test_stocks_rule_engine_integrates_adr_gate():
    """Valida la integración completa del filtro ADR y anti-lateralidad en StocksRuleEngine."""
    engine = StocksRuleEngine.get_instance()

    rule = {
        'rule_code': 'HOT_BB_PULLBACK_5M',
        'group_name': 'inversiones_hot',
        'direction': 'buy',
        'order_type': 'market',
        'movements_allowed': ['ascending', 'lateral_ascending', 'asc_from_low'],
        'rvol_min': 1.2
    }

    # Contexto 1: Bloqueo por movimiento lateral
    ctx_lateral = {
        'ticker': 'SBS',
        'price': 6.38,
        'movement_type': 'lateral',
        'adr_14_pct': 5.0,
        'adr_consumed_pct': 40.0,
        'rvol': 1.5,
        'bandwidth_15m': 3.0,
        'candle_vol_15m': 20_000.0
    }
    res1 = engine.evaluate_rule(rule, ctx_lateral)
    assert res1['triggered'] is False
    assert any("Anti-Lateralidad" in f or "no en" in f for f in res1['failures'])

    # Contexto 2: Bloqueo por ADR insuficiente (tipo SBS 2.45%)
    ctx_low_adr = {
        'ticker': 'SBS',
        'price': 6.38,
        'movement_type': 'ascending',
        'adr_14_pct': 2.45,
        'adr_consumed_pct': 40.0,
        'rvol': 1.5,
        'bandwidth_15m': 3.0,
        'candle_vol_15m': 20_000.0
    }
    res2 = engine.evaluate_rule(rule, ctx_low_adr)
    assert res2['triggered'] is False
    assert any("ADR 14D insuficiente" in f for f in res2['failures'])
