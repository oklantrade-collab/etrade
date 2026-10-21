"""
Unit Tests for Sprint Enhancements (21-Oct-2026):
1. Re-buy blocking above Upper Bollinger on compressed 15m candles (< 0.4 ATR).
2. Re-buy blocking when RSI 15m > 70 without volume/expansion justification.
3. 15m Lateral Exhaustion detection ("El precio no quiere subir más").
4. Stepped Delta Trailing SL during lateral consolidation.
5. 5-Minute Price Velocity Metric (V5m) and Stagnation Exit.
6. Options 15m EMA3 flattening near Bollinger Upper (SPY CALL take profit).
"""

import os
import sys
sys.path.append(os.path.abspath("backend"))

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from app.stocks.aduana_gap_runner_engine import (
    evaluate_gap_runner_entry_tranches,
    evaluate_gap_runner_aduana_exit,
    compute_price_velocity_5m
)
from app.options.exit_engine import evaluate_technical_rules_and_stops


def _make_df(candles: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col not in df.columns:
            df[col] = 10.0
    return df


def test_rebuy_blocked_above_bollinger_on_compressed_candle():
    """Problema 1: Recompra bloqueada sobre Bollinger Superior si la vela es pequeña/comprimida."""
    c_15m = []
    for _ in range(20):
        c_15m.append({'open': 9.8, 'high': 10.2, 'low': 9.7, 'close': 10.0, 'volume': 50000})
    # Vela actual comprimida sobre el Bollinger Superior (~10.3)
    c_15m.append({'open': 10.98, 'high': 11.02, 'low': 10.97, 'close': 11.00, 'volume': 30000})
    df_15m = _make_df(c_15m)

    df_5m = _make_df([{'open': 10.95, 'high': 11.05, 'low': 10.95, 'close': 11.00, 'volume': 20000}] * 6)
    df_1h = _make_df([{'open': 9.5, 'high': 12.0, 'low': 9.4, 'close': 11.0, 'volume': 300000}] * 25)

    active_pos = {
        'id': 'pos-test',
        'ticker': 'WULF',
        'status': 'open',
        'dca_count': 0,
        'avg_price': 10.50,
        'stop_loss': 10.00,
        'shares': 50
    }

    res = evaluate_gap_runner_entry_tranches(
        ticker="WULF",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=20.0,
        active_position=active_pos
    )

    assert res['should_enter'] is False
    assert "Bollinger Superior" in res['reason']
    assert "Vela comprimida" in res['reason']


def test_rebuy_blocked_when_rsi15m_above_70_without_rvol():
    """Problema 1: Recompra sobre Bollinger con RSI > 70 bloqueada si RVOL < 2.0x."""
    c_15m = []
    # Trend ascending to create high RSI
    for i in range(20):
        p = 10.0 + (i * 0.1)
        c_15m.append({'open': p - 0.05, 'high': p + 0.1, 'low': p - 0.1, 'close': p, 'volume': 50000})
    # Last candle clearly above BB Upper (~12.2) with moderate volume (RVOL ~ 1.0x) and small expansion
    c_15m.append({'open': 12.6, 'high': 12.8, 'low': 12.5, 'close': 12.7, 'volume': 45000})
    df_15m = _make_df(c_15m)

    df_5m = _make_df([{'open': 12.6, 'high': 12.8, 'low': 12.5, 'close': 12.7, 'volume': 20000}] * 6)
    df_1h = _make_df([{'open': 9.5, 'high': 16.0, 'low': 9.4, 'close': 12.7, 'volume': 300000}] * 25)

    active_pos = {
        'id': 'pos-test2',
        'ticker': 'WULF',
        'status': 'open',
        'dca_count': 0,
        'avg_price': 11.50,
        'stop_loss': 11.00,
        'shares': 50
    }

    res = evaluate_gap_runner_entry_tranches(
        ticker="WULF",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=25.0,
        active_position=active_pos
    )

    assert res['should_enter'] is False
    assert "RSI 15m" in res['reason'] or "Bollinger" in res['reason']


def test_15m_lateral_exhaustion_blocks_rebuys():
    """Problema 2: Detección de Agotamiento Lateral en 15m bloquea recompras."""
    c_15m = []
    for _ in range(20):
        c_15m.append({'open': 10.0, 'high': 10.5, 'low': 9.8, 'close': 10.2, 'volume': 50000})
    # 2 velas consecutivas planas con rango mínimo
    c_15m.append({'open': 10.20, 'high': 10.22, 'low': 10.19, 'close': 10.20, 'volume': 20000})
    c_15m.append({'open': 10.20, 'high': 10.21, 'low': 10.19, 'close': 10.20, 'volume': 18000})
    df_15m = _make_df(c_15m)

    df_5m = _make_df([{'open': 10.18, 'high': 10.22, 'low': 10.18, 'close': 10.20, 'volume': 15000}] * 6)
    df_1h = _make_df([{'open': 9.5, 'high': 11.0, 'low': 9.4, 'close': 10.2, 'volume': 300000}] * 25)

    active_pos = {
        'id': 'pos-lateral',
        'ticker': 'AHT',
        'status': 'open',
        'dca_count': 0,
        'avg_price': 10.00,
        'stop_loss': 9.50,
        'shares': 100
    }

    res = evaluate_gap_runner_entry_tranches(
        ticker="AHT",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=20.0,
        active_position=active_pos
    )

    assert res['should_enter'] is False
    assert "Agotamiento Lateral 15m" in res['reason']


def test_stepped_delta_trailing_sl_on_lateral_consolidation():
    """Problema 3: Trailing Stop Escalonado ancla SL a Precio Entrada + n*Deltas durante lateralidad."""
    c_15m = []
    for _ in range(20):
        c_15m.append({'open': 10.0, 'high': 10.5, 'low': 9.8, 'close': 10.2, 'volume': 50000})
    # Lateral en 10.80 (sin disparar RSI > 80)
    c_15m.append({'open': 10.80, 'high': 10.83, 'low': 10.78, 'close': 10.80, 'volume': 20000})
    c_15m.append({'open': 10.80, 'high': 10.82, 'low': 10.79, 'close': 10.80, 'volume': 22000})
    df_15m = _make_df(c_15m)

    active_pos = {
        'avg_price': 10.00,
        'highest_price_reached': 11.10,
        'stop_loss': 9.80,
        'shares': 100,
        'gap_pct': 10.0,
        'tp_block1_executed': True  # TP1 ya fue tomado previamente
    }

    exit_eval = evaluate_gap_runner_aduana_exit(
        position=active_pos,
        current_price=10.80,
        df_15m=df_15m
    )

    assert exit_eval['new_stop_loss'] is not None
    assert exit_eval['new_stop_loss'] > 10.00  # Stop Loss por encima de precio de entrada
    assert exit_eval['rule_code'] == "ADUANA_GAP_TRAIL_LATERAL_DELTA"


def test_price_velocity_stagnation_exit_5m():
    """Problema 4: Cierre defensivo si 3 velas de 5m consecutivas tienen velocidad Baja/Muy Baja cerca a máximos."""
    # 5m velas con variación ínfima (estancamiento < 0.15% cada una)
    c_5m = [
        {'open': 12.0, 'high': 12.5, 'low': 11.8, 'close': 12.4, 'volume': 50000},
        {'open': 12.4, 'high': 12.55, 'low': 12.35, 'close': 12.50, 'volume': 40000},
        {'open': 12.50, 'high': 12.51, 'low': 12.49, 'close': 12.50, 'volume': 15000},  # V1: 0.0%
        {'open': 12.50, 'high': 12.52, 'low': 12.48, 'close': 12.51, 'volume': 12000},  # V2: +0.08%
        {'open': 12.51, 'high': 12.52, 'low': 12.49, 'close': 12.50, 'volume': 11000},  # V3: -0.08%
    ]
    df_5m = _make_df(c_5m)

    vel = compute_price_velocity_5m(df_5m)
    assert vel['is_stagnant'] is True
    assert vel['consecutive_low'] >= 3

    active_pos = {
        'avg_price': 11.00,
        'highest_price_reached': 12.55,
        'stop_loss': 10.50,
        'shares': 100,
        'gap_pct': 25.0
    }

    exit_eval = evaluate_gap_runner_aduana_exit(
        position=active_pos,
        current_price=12.50,
        df_5m=df_5m
    )

    assert exit_eval['should_exit'] is True
    assert exit_eval['rule_code'] == "ADUANA_VELOCITY_STAGNATION_EXIT"
    assert "Salida Defensiva por Estancamiento" in exit_eval['reason']


def test_options_exit_ema3_flat_near_bb_upper_15m():
    """Problema 5: Salida CALL de opciones cuando EMA3 15m se aplana cerca a Banda Bollinger Superior."""
    tech_context = {
        "valid": True,
        "current_price": 772.80,  # Cerca a bb_upper_15m (773.00)
        "ema3_15m": 772.50,
        "ema9_15m": 770.00,
        "ema3_slope_15m": 0.01,  # Aplanada (<= 0.02%)
        "bb_upper_15m": 773.00,
        "rsi_1h": 65.0,
        "ema3_slope_1h": 0.15,   # En 1H sigue positiva, pero en 15m ya se aplanó
        "is_sipv_sell_15m": False,
        "is_sipv_sell_1h": False
    }

    position = {
        "symbol": "SPY",
        "strategy_type": "long_call",
        "entry_debit": 5.00,
        "qty": 1,
        "exit_plan": {}
    }

    should_exit, rule, details = evaluate_technical_rules_and_stops(
        position=position,
        tech=tech_context,
        now_dt=datetime.now(timezone.utc)
    )

    assert should_exit is True
    assert rule == "ema3_flat_near_bb_upper_15m"
    assert "EMA3 15m aplanada" in details['detail']
