"""
Unit & Integration Tests — TRAP SHIELD & INTRADAY ALPHA PRIORITY ENGINE
========================================================================
Valida la exclusión matemática y operativa de trampas de apertura ("Gap & Crap")
y la inyección de prioridad alta (Rank 98.5) para runners intradía.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import pandas as pd
import numpy as np

from app.stocks.trap_shield import (
    calculate_intraday_vwap,
    evaluate_opening_range_5m,
    evaluate_trap_shield,
    calculate_intraday_potential_growth,
)
from app.stocks.stocks_orchestrator import (
    calculate_composite_rank,
    is_overbought,
)


def _create_5m_candles(opens, highs, lows, closes, volumes):
    return pd.DataFrame({
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })


# ════════════════════════════════════════════════════════════
# 1. TEST VWAP INTRADÍA
# ════════════════════════════════════════════════════════════

def test_calculate_intraday_vwap():
    df = _create_5m_candles(
        opens=[10.0, 10.5],
        highs=[10.6, 11.0],
        lows=[9.9, 10.4],
        closes=[10.4, 10.8],
        volumes=[1000, 2000]
    )
    # typical_1 = (10.6 + 9.9 + 10.4)/3 = 10.3 -> pv = 10300
    # typical_2 = (11.0 + 10.4 + 10.8)/3 = 10.7333 -> pv = 21466.67
    # vwap = (10300 + 21466.67) / 3000 = 10.5888
    vwap = calculate_intraday_vwap(df)
    assert round(vwap, 2) == 10.59


# ════════════════════════════════════════════════════════════
# 2. TEST OPENING RANGE BREAKOUT (5m)
# ════════════════════════════════════════════════════════════

def test_opening_range_red_candle_breakdown():
    # Vela 1 roja (Open 10.0, Close 9.5, High 10.2, Low 9.4)
    # Vela 2 perfora el mínimo de apertura (Low 9.4 -> Close 9.2)
    df = _create_5m_candles(
        opens=[10.0, 9.4],
        highs=[10.2, 9.6],
        lows=[9.4, 9.1],
        closes=[9.5, 9.2],
        volumes=[50000, 30000]
    )
    res = evaluate_opening_range_5m(df)
    assert res['has_orb'] is True
    assert res['first_candle_red'] is True
    assert res['orb_low'] == 9.1
    # Precio actual en 9.2 perforó el low de vela 1 (9.4)
    assert res['cur_close'] == 9.2


# ════════════════════════════════════════════════════════════
# 3. TEST TRAP SHIELD — CASOS TRAMPA REALES
# ════════════════════════════════════════════════════════════

def test_trap_shield_excessive_gap_fade():
    """Caso real AEMD (+493% gap que colapsa por debajo del open y vwap)."""
    # PrevClose 1.43 -> Open 8.48 (Gap +493%) -> Precio actual 6.78
    df_5m = _create_5m_candles(
        opens=[8.48, 8.00],
        highs=[9.50, 8.20],
        lows=[7.80, 6.70],
        closes=[7.90, 6.78],
        volumes=[1000000, 800000]
    )
    res = evaluate_trap_shield(
        current_price=6.78,
        prev_close=1.43,
        open_price=8.48,
        df_5m=df_5m,
        rvol=28.0,
        news_tier=2
    )
    assert res['is_trap'] is True
    assert res['trap_type'] == 'EXCESSIVE_GAP_FADE'
    assert res['is_intraday_alpha'] is False


def test_trap_shield_red_opening_candle_breakdown():
    """Caso real PDSB día 1 (+121% gap con vela roja que rompe soporte)."""
    # PrevClose 0.22 -> Open 0.49 (Gap +122%) -> Precio actual 0.30
    df_5m = _create_5m_candles(
        opens=[0.49, 0.40, 0.35],
        highs=[0.65, 0.42, 0.36],
        lows=[0.45, 0.34, 0.28],
        closes=[0.46, 0.35, 0.30],
        volumes=[500000, 300000, 200000]
    )
    res = evaluate_trap_shield(
        current_price=0.30,
        prev_close=0.22,
        open_price=0.49,
        df_5m=df_5m,
        rvol=15.0,
        news_tier=2
    )
    assert res['is_trap'] is True
    assert res['is_intraday_alpha'] is False


def test_trap_shield_below_vwap_trap():
    """Acción con gap del 30% pero cotizando por debajo de VWAP."""
    # VWAP en 11.20, precio actual en 10.50
    df_5m = _create_5m_candles(
        opens=[11.0, 11.5, 10.8],
        highs=[11.8, 11.6, 11.0],
        lows=[10.9, 11.0, 10.4],
        closes=[11.5, 11.1, 10.5],
        volumes=[50000, 40000, 30000]
    )
    res = evaluate_trap_shield(
        current_price=10.50,
        prev_close=8.00,
        open_price=11.00,
        df_5m=df_5m,
        rvol=3.5,
        news_tier=2
    )
    assert res['is_trap'] is True
    assert res['trap_type'] in ['BELOW_VWAP', 'RED_DAILY_CANDLE_BELOW_OPEN']


# ════════════════════════════════════════════════════════════
# 4. TEST TRAP SHIELD — CASOS RUNNERS REALES (ALTA PRIORIDAD)
# ════════════════════════════════════════════════════════════

def test_trap_shield_sweet_spot_runner_wff():
    """Caso real WFF: Gap plano (+1.5%), RVOL masivo, cotizando sobre VWAP."""
    # PrevClose 2.05 -> Open 2.08 -> Precio actual 3.50 (corriendo intradía)
    df_5m = _create_5m_candles(
        opens=[2.08, 2.20, 2.80],
        highs=[2.30, 2.90, 3.60],
        lows=[2.05, 2.15, 2.75],
        closes=[2.25, 2.85, 3.50],
        volumes=[200000, 500000, 800000]
    )
    res = evaluate_trap_shield(
        current_price=3.50,
        prev_close=2.05,
        open_price=2.08,
        df_5m=df_5m,
        rvol=25.0,
        news_tier=2,
        bands_15m={'upper_5': 5.20}
    )
    assert res['is_trap'] is False
    assert res['is_sweet_spot'] is True
    assert res['is_intraday_alpha'] is True
    assert res['priority_rank_boost'] == 98.5
    assert res['growth_potential_pct'] >= 5.0


def test_trap_shield_sweet_spot_runner_meds():
    """Caso real MEDS Día 1: Gap +3.5%, RVOL 8x, precio sobre VWAP y potencial alto."""
    # PrevClose 0.87 -> Open 0.89 -> Precio actual 1.25
    df_5m = _create_5m_candles(
        opens=[0.89, 0.95, 1.10],
        highs=[0.98, 1.15, 1.30],
        lows=[0.88, 0.94, 1.08],
        closes=[0.96, 1.12, 1.25],
        volumes=[100000, 250000, 400000]
    )
    res = evaluate_trap_shield(
        current_price=1.25,
        prev_close=0.87,
        open_price=0.89,
        df_5m=df_5m,
        rvol=8.5,
        news_tier=1,
        bands_15m={'upper_5': 2.10}
    )
    assert res['is_trap'] is False
    assert res['is_sweet_spot'] is True
    assert res['is_intraday_alpha'] is True
    assert res['growth_potential_pct'] >= 10.0


# ════════════════════════════════════════════════════════════
# 5. TEST ORCHESTRATOR — COMPOSITE RANK & BLOQUEO SOBRECOMPRA
# ════════════════════════════════════════════════════════════

def test_orchestrator_composite_rank_intraday_alpha():
    """Verifica que un candidato con is_intraday_alpha reciba Rank 98.5."""
    cfg = {'apex_composite_w_4h': 0.30, 'apex_composite_w_1d': 0.25}
    rank = calculate_composite_rank(
        apex_4h=80.0,
        apex_1d=75.0,
        return_pct=5.0,
        confidence='high',
        rvol=3.0,
        cfg=cfg,
        is_intraday_alpha=True
    )
    assert rank == 98.5


def test_orchestrator_blocks_trap():
    """Verifica que is_overbought bloquee automáticamente candidatos con is_trap=True."""
    snap = {
        'price': 10.0,
        'rsi_14': 55.0,
        'fib_zone_15m': 2,
        'upper_3': 12.0,
        'is_trap': True,
        'trap_reason': 'Gap masivo desinflándose bajo VWAP'
    }
    res = is_overbought(snap, cfg={'apex_max_overbought_rsi': 75, 'apex_max_fib_zone': 3})
    assert res['blocked'] is True
    assert 'Trap Shield' in res['reason']
