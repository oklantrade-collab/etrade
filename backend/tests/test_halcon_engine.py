"""
Unit tests for HALCÓN Engine & Scoring layers.
"""
import pytest
import pandas as pd
import numpy as np

from app.halcon_centinela.config import (
    HALCON_PARAMS, PERFIL_ALTA_VOLATILIDAD, PERFIL_TENDENCIA_SOSTENIDA,
    Semaforo, CentinelaDecision, classify_entry_profile, get_profile
)
from app.halcon_centinela.halcon_engine import HalconEngine
from app.halcon_centinela.scoring.score_1d import calculate_score_1d
from app.halcon_centinela.scoring.score_4h import calculate_score_4h
from app.halcon_centinela.scoring.score_15m import calculate_score_15m
from app.halcon_centinela.scoring.score_5m import calculate_score_5m
from app.halcon_centinela.scoring.score_1m import calculate_score_1m
from app.halcon_centinela.scoring.rsi_component import calculate_rsi_adjustment
from app.halcon_centinela.scoring.regime_filter import classify_regime, apply_regime_adjustments
from app.halcon_centinela.scoring.compression_index import (
    calculate_compression_index, apply_fibonacci_multiplier, select_compression_timeframe
)
from app.halcon_centinela.scoring.volume_confirmation import check_volume_confirmation


def test_classify_entry_profile():
    # High volatility: ADX > 30 and ATR% > 0.8%
    profile = classify_entry_profile(adx=35.0, atr_pct_daily=0.012)
    assert profile.value == 'ALTA_VOLATILIDAD'
    
    # Moderate: ADX < 30
    profile_mod = classify_entry_profile(adx=22.0, atr_pct_daily=0.012)
    assert profile_mod.value == 'TENDENCIA_SOSTENIDA'


def test_score_1d_bollinger_extreme():
    # Price above upper_6 band -> score should indicate extreme
    df_1d = pd.DataFrame([
        {'open': 100, 'high': 105, 'low': 99, 'close': 104, 'upper_6': 103, 'lower_6': 95, 'basis': 100, 'ema_3': 102},
        {'open': 104, 'high': 108, 'low': 103, 'close': 107, 'upper_6': 105, 'lower_6': 95, 'basis': 100, 'ema_3': 104},
        {'open': 107, 'high': 110, 'low': 106, 'close': 109, 'upper_6': 106, 'lower_6': 95, 'basis': 100, 'ema_3': 106},
        {'open': 109, 'high': 112, 'low': 108, 'close': 111, 'upper_6': 107, 'lower_6': 95, 'basis': 100, 'ema_3': 108},
        {'open': 111, 'high': 113, 'low': 110, 'close': 112, 'upper_6': 108, 'lower_6': 95, 'basis': 100, 'ema_3': 110},
        {'open': 112, 'high': 113, 'low': 111, 'close': 112.5, 'upper_6': 109, 'lower_6': 95, 'basis': 100, 'ema_3': 111}  # forming
    ])
    res = calculate_score_1d(df_1d, 'long', HALCON_PARAMS)
    assert isinstance(res, dict)
    assert 'score' in res
    assert res['components']['bollinger'] == 40


def test_score_4h_ema3_slope():
    # Descending EMA3 -> negative score for long
    df_4h = pd.DataFrame([
        {'open': 100, 'high': 102, 'low': 98, 'close': 99, 'ema_3': 105},
        {'open': 99, 'high': 100, 'low': 96, 'close': 97, 'ema_3': 103},
        {'open': 97, 'high': 98, 'low': 94, 'close': 95, 'ema_3': 100},
        {'open': 95, 'high': 96, 'low': 92, 'close': 93, 'ema_3': 98},
        {'open': 93, 'high': 94, 'low': 91, 'close': 92, 'ema_3': 96},
        {'open': 92, 'high': 93, 'low': 90, 'close': 91, 'ema_3': 95} # forming
    ])
    res = calculate_score_4h(df_4h, 'long', HALCON_PARAMS)
    assert res['score'] == -60
    assert res['components']['ema3_slope'] == -60


def test_score_15m_hh_ll():
    # Ascending lows + EMA3 > EMA9 -> bullish for long (+50)
    df_15m = pd.DataFrame([
        {'open': 100, 'high': 102, 'low': 98, 'close': 101, 'ema_3': 101, 'ema_9': 100, 'ema_20': 99},
        {'open': 101, 'high': 103, 'low': 99, 'close': 102, 'ema_3': 102, 'ema_9': 100.5, 'ema_20': 99.5},
        {'open': 102, 'high': 104, 'low': 100, 'close': 103, 'ema_3': 103, 'ema_9': 101, 'ema_20': 100},
        {'open': 103, 'high': 105, 'low': 101, 'close': 104, 'ema_3': 104, 'ema_9': 101.5, 'ema_20': 100.5},
        {'open': 104, 'high': 106, 'low': 102, 'close': 105, 'ema_3': 105, 'ema_9': 102, 'ema_20': 101},  # forming
    ])
    res = calculate_score_15m(df_15m, 'long', HALCON_PARAMS)
    assert res['score'] >= 50


def test_rsi_adjustment_and_divergence():
    # Oversold RSI < 20
    df_rsi = pd.DataFrame([
        {'open': 100, 'high': 101, 'low': 99, 'close': 99.5, 'rsi': 18},
        {'open': 99.5, 'high': 100, 'low': 98.5, 'close': 99, 'rsi': 17},
        {'open': 99, 'high': 99.5, 'low': 98, 'close': 98.5, 'rsi': 16},
        {'open': 98.5, 'high': 99, 'low': 97.5, 'close': 98, 'rsi': 15},
    ])
    adj = calculate_rsi_adjustment(df_rsi, '15m', 'moderate', 'TENDENCIA_SOSTENIDA', HALCON_PARAMS)
    assert adj == 25  # Oversold -> +25 points


def test_regime_classification():
    # Choppy regime (ADX < 15)
    r_choppy = classify_regime(adx=12.0, plus_di=18.0, minus_di=20.0)
    assert r_choppy['regime'] == 'choppy'
    assert r_choppy['ema_cross_weight_mult'] == 0.5

    # Strong trend regime (ADX > 30)
    r_strong = classify_regime(adx=38.0, plus_di=32.0, minus_di=14.0)
    assert r_strong['regime'] == 'strong_trend'
    assert r_strong['macro_weight_boost'] == 1.2


def test_compression_index():
    df_comp = pd.DataFrame([
        {'ema_3': 100.05, 'ema_9': 100.0, 'ema_20': 100.8, 'close': 100.0},
        {'ema_3': 100.04, 'ema_9': 100.0, 'ema_20': 100.8, 'close': 100.0},
        {'ema_3': 100.03, 'ema_9': 100.0, 'ema_20': 100.8, 'close': 100.0},
    ])
    # D1 = |100.8 - 100.0| = 0.8
    # D2 = |100.03 - 100.0| = 0.03
    # Index = 0.03 / 0.8 = 0.0375 < 0.15 -> compressed
    res = calculate_compression_index(df_comp, atr_daily=1.5, params=HALCON_PARAMS)
    assert res['compressed'] == True
    assert res['index'] < 0.15


def test_halcon_engine_full_evaluation():
    engine = HalconEngine(HALCON_PARAMS)

    # Position in profit
    pos = {
        'id': 'test_pos_1',
        'symbol': 'EURUSD',
        'direction': 'long',
        'entry_price': 1.0800,
        'current_price': 1.0850,
        'current_pnl': 5.0,  # $5 profit > $1 min
        'position_size': 0.1,
        'entry_profile': 'TENDENCIA_SOSTENIDA'
    }

    # Market data with strong bearish signals (should trigger CIERRE_TOTAL for LONG)
    df_1d = pd.DataFrame([
        {'open': 1.09, 'high': 1.095, 'low': 1.08, 'close': 1.082, 'upper_6': 1.09, 'lower_6': 1.07, 'basis': 1.08, 'ema_3': 1.083, 'atr': 0.006},
        {'open': 1.082, 'high': 1.085, 'low': 1.075, 'close': 1.078, 'upper_6': 1.09, 'lower_6': 1.07, 'basis': 1.08, 'ema_3': 1.081, 'atr': 0.006},
        {'open': 1.078, 'high': 1.08, 'low': 1.07, 'close': 1.072, 'upper_6': 1.09, 'lower_6': 1.07, 'basis': 1.08, 'ema_3': 1.077, 'atr': 0.006},
        {'open': 1.072, 'high': 1.074, 'low': 1.068, 'close': 1.070, 'upper_6': 1.09, 'lower_6': 1.07, 'basis': 1.08, 'ema_3': 1.073, 'atr': 0.006},
        {'open': 1.070, 'high': 1.072, 'low': 1.066, 'close': 1.068, 'upper_6': 1.09, 'lower_6': 1.07, 'basis': 1.08, 'ema_3': 1.069, 'atr': 0.006},
    ])
    df_4h = pd.DataFrame([
        {'open': 1.085, 'high': 1.086, 'low': 1.080, 'close': 1.081, 'ema_3': 1.084},
        {'open': 1.081, 'high': 1.082, 'low': 1.078, 'close': 1.079, 'ema_3': 1.082},
        {'open': 1.079, 'high': 1.080, 'low': 1.074, 'close': 1.075, 'ema_3': 1.078},
        {'open': 1.075, 'high': 1.076, 'low': 1.070, 'close': 1.071, 'ema_3': 1.074},
        {'open': 1.071, 'high': 1.072, 'low': 1.068, 'close': 1.069, 'ema_3': 1.070},
    ])
    df_15m = pd.DataFrame([
        {'open': 1.080, 'high': 1.082, 'low': 1.078, 'close': 1.079, 'ema_3': 1.078, 'ema_9': 1.081, 'ema_20': 1.083, 'volume': 100, 'adx': 25.0, 'plus_di': 15.0, 'minus_di': 28.0, 'rsi': 35},
        {'open': 1.079, 'high': 1.080, 'low': 1.075, 'close': 1.076, 'ema_3': 1.076, 'ema_9': 1.080, 'ema_20': 1.082, 'volume': 120, 'adx': 26.0, 'plus_di': 14.0, 'minus_di': 30.0, 'rsi': 32},
        {'open': 1.076, 'high': 1.077, 'low': 1.072, 'close': 1.073, 'ema_3': 1.073, 'ema_9': 1.078, 'ema_20': 1.081, 'volume': 150, 'adx': 27.0, 'plus_di': 13.0, 'minus_di': 32.0, 'rsi': 29},
        {'open': 1.073, 'high': 1.074, 'low': 1.069, 'close': 1.070, 'ema_3': 1.070, 'ema_9': 1.076, 'ema_20': 1.080, 'volume': 160, 'adx': 28.0, 'plus_di': 12.0, 'minus_di': 34.0, 'rsi': 26},
    ])
    df_5m = pd.DataFrame([
        {'open': 1.075, 'high': 1.076, 'low': 1.072, 'close': 1.073, 'ema_3': 1.072, 'ema_9': 1.075, 'ema_20': 1.078, 'basis': 1.076, 'upper_6': 1.085, 'lower_6': 1.065, 'rsi': 30},
        {'open': 1.073, 'high': 1.074, 'low': 1.070, 'close': 1.071, 'ema_3': 1.070, 'ema_9': 1.074, 'ema_20': 1.077, 'basis': 1.075, 'upper_6': 1.085, 'lower_6': 1.065, 'rsi': 28},
        {'open': 1.071, 'high': 1.072, 'low': 1.068, 'close': 1.069, 'ema_3': 1.068, 'ema_9': 1.073, 'ema_20': 1.076, 'basis': 1.074, 'upper_6': 1.085, 'lower_6': 1.065, 'rsi': 25},
    ])
    df_1m = pd.DataFrame([
        {'open': 1.070, 'high': 1.071, 'low': 1.068, 'close': 1.069, 'ema_3': 1.068, 'ema_9': 1.070, 'atr': 0.0005},
        {'open': 1.069, 'high': 1.070, 'low': 1.067, 'close': 1.068, 'ema_3': 1.067, 'ema_9': 1.069, 'atr': 0.0005},
    ])

    market_data = {
        'df_1d': df_1d,
        'df_4h': df_4h,
        'df_15m': df_15m,
        'df_5m': df_5m,
        'df_1m': df_1m,
    }

    result = engine.evaluate(pos, market_data)
    assert result.score_final <= -25.0  # Bearish pressure against LONG (Rojo Débil)
    assert result.semaforo == Semaforo.ROJO_DEBIL.value
