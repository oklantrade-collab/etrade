"""
Test Suite: Stocks Solo LONGs con Filtros de Alta Fuerza de Compra,
Entradas en 1 HORA (Pullback / Clímax) y Salida ADUANA EMA3 + BB (1H/4H)
======================================================================
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import pandas as pd
import numpy as np

from app.stocks.buying_force_detector import (
    evaluate_macro_1d_alignment,
    calculate_buying_force_score,
    detect_candle_absorption,
    detect_pullback_and_climax_1h
)
from app.stocks.stocks_rule_engine import StocksRuleEngine
from app.stocks.stocks_orchestrator import calculate_composite_rank
from app.stocks.aduana_stocks_exit_engine import (
    evaluate_aduana_stocks_exit,
    calculate_1h_trailing_stop
)


def create_ohlc(prices, volumes=None, high_mult=1.002, low_mult=0.998, open_mult=0.999):
    n = len(prices)
    if volumes is None:
        volumes = [50000.0] * n
    return pd.DataFrame({
        'open': [p * open_mult for p in prices],
        'high': [p * high_mult for p in prices],
        'low': [p * low_mult for p in prices],
        'close': prices,
        'volume': volumes
    })


# ── TEST 1: Macro 1D Alignment (EMA20 > EMA50 > EMA200) ──
def test_macro_1d_alignment():
    # Caso Alcista Acelerado: Tendencia alcista clara
    prices_bullish = [100.0 + (i * 0.5) for i in range(220)]
    df_bull = create_ohlc(prices_bullish)
    res_bull = evaluate_macro_1d_alignment(df_bull)
    assert res_bull['aligned'] is True
    assert res_bull['ema20'] > res_bull['ema50'] > res_bull['ema200']

    # Caso Bajista: Tendencia a la baja
    prices_bearish = [200.0 - (i * 0.5) for i in range(220)]
    df_bear = create_ohlc(prices_bearish)
    res_bear = evaluate_macro_1d_alignment(df_bear)
    assert res_bear['aligned'] is False


# ── TEST 2: Absorción y Vela de Rechazo ──
def test_candle_absorption():
    # Vela Martillo / Rechazo con mecha inferior grande (Open 102, High 103, Low 98, Close 102.5)
    # Rango = 5.0, mecha inferior = 102 - 98 = 4.0 (80% del rango)
    abs_res = detect_candle_absorption(open_p=102.0, high_p=103.0, low_p=98.0, close_p=102.5)
    assert abs_res['has_absorption'] is True
    assert abs_res['lower_wick_pct'] >= 35.0

    # Vela Bajista Sólida sin absorción (Open 103, High 103.2, Low 99.8, Close 100.0)
    no_abs = detect_candle_absorption(open_p=103.0, high_p=103.2, low_p=99.8, close_p=100.0)
    assert no_abs['has_absorption'] is False


# ── TEST 3: Buying Force Score ──
def test_buying_force_score():
    # Activo Ultra Dinámico: ADR 5.5%, Consumo 40%, RVOL 2.2x, Macro Alineada
    prices_1h = [150.0 + (i * 0.3) for i in range(30)]
    df_1h = create_ohlc(prices_1h)

    res = calculate_buying_force_score(
        adr_pct=5.5,
        consumed_pct=40.0,
        rvol_1h=2.2,
        df_1h=df_1h,
        macro_aligned=True,
        bandwidth_1h=4.5
    )
    assert res['score'] >= 70
    assert res['is_qualified'] is True

    # Activo Aletargado: ADR 1.8%, Consumo 85%, RVOL 0.6x, Macro Desalineada
    res_mediocre = calculate_buying_force_score(
        adr_pct=1.8,
        consumed_pct=85.0,
        rvol_1h=0.6,
        df_1h=df_1h,
        macro_aligned=False,
        bandwidth_1h=1.2
    )
    assert res_mediocre['score'] < 50
    assert res_mediocre['is_qualified'] is False


# ── TEST 4: Entradas en 1 HORA (Pullback y Clímax) ──
def test_pullback_and_climax_1h():
    # Simular DataFrame 1H con soporte en EMA9
    prices_1h = [100.0 + (i * 0.2) for i in range(25)]
    df_1h = create_ohlc(prices_1h)
    
    # Precio actual justo en la EMA9 de 1H
    close_s = df_1h['close']
    ema9_val = float(close_s.ewm(span=9, adjust=False).mean().iloc[-1])
    
    entry_res = detect_pullback_and_climax_1h(
        current_price=ema9_val,
        df_1h=df_1h,
        macro_aligned=True
    )
    assert entry_res['triggered'] is True
    assert entry_res['route'] == 'PULLBACK'
    assert entry_res['support_level'] in ('EMA3', 'EMA9', 'EMA20')


# ── TEST 5: StocksRuleEngine - LONG_PULLBACK_1H y LONG_CLIMAX_1H ──
def test_stocks_rule_engine_pullback_1h():
    re = StocksRuleEngine.get_instance()

    # Contexto válido para LONG_PULLBACK_1H
    valid_ctx = {
        'ticker': 'NVDA',
        'price': 130.0,
        'rvol': 2.0,
        'macro_1d_aligned': True,
        'buying_force_score': 88,
        'adr_14_pct': 4.5,
        'entry_route_1h': 'PULLBACK',
        'entry_support_1h': 'EMA9',
        'pool_type': 'HOT',
        'is_ema3_1h_ascending': True,
        'ema3_slope_1h': 0.15
    }

    rule_obj = {
        'rule_code': 'LONG_PULLBACK_1H',
        'direction': 'buy',
        'order_type': 'market',
        'enabled': True
    }

    eval_ok = re.evaluate_rule(rule_obj, valid_ctx)
    assert eval_ok['triggered'] is True

    # Si la Macro 1D no está alineada -> DEBE FALLAR
    invalid_ctx = {**valid_ctx, 'macro_1d_aligned': False}
    eval_fail = re.evaluate_rule(rule_obj, invalid_ctx)
    assert eval_fail['triggered'] is False
    assert any("Macro 1D Desalineada" in f for f in eval_fail['failures'])

    # Si el Buying Force es mediocre (< 70) -> DEBE FALLAR
    low_bf_ctx = {**valid_ctx, 'buying_force_score': 55}
    eval_fail_bf = re.evaluate_rule(rule_obj, low_bf_ctx)
    assert eval_fail_bf['triggered'] is False
    assert any("Buying Force Insuficiente" in f for f in eval_fail_bf['failures'])


# ── TEST 6: Boost de Alta Prioridad en Composite Rank ──
def test_composite_rank_high_growth_boost():
    cfg = {}
    # Rank base normal
    rank_base = calculate_composite_rank(
        apex_4h=65.0, apex_1d=60.0, return_pct=2.0, confidence='medium', rvol=1.5, cfg=cfg
    )

    # Rank con alto crecimiento y buying force >= 85
    rank_boosted = calculate_composite_rank(
        apex_4h=65.0, apex_1d=60.0, return_pct=2.0, confidence='medium', rvol=1.5, cfg=cfg,
        buying_force_score=88, is_high_priority_growth=True
    )

    assert rank_boosted > rank_base
    assert rank_boosted >= 95.0


# ── TEST 7: Salida ADUANA EMA3 + BB y Trailing Stop 1H en Stocks ──
def test_aduana_stocks_exit_and_1h_trailing():
    # 1. Trailing Stop en velas de 1H
    pos = {
        'symbol': 'TSLA',
        'side': 'long',
        'entry_price': 200.0,
        'stop_loss': 195.0,
        'shares': 10
    }

    # DataFrame 1H en rally alcista
    prices_1h = [200.0 + (i * 1.5) for i in range(25)]
    df_1h = create_ohlc(prices_1h)

    trail_res = calculate_1h_trailing_stop(pos, current_price=236.0, df_1h=df_1h)
    assert trail_res['should_update'] is True
    assert trail_res['new_sl'] > pos['stop_loss']
    assert trail_res['new_sl'] < 236.0

    # 2. Salida ADUANA Trend Exit integrada en evaluate_aduana_stocks_exit
    # Inflexión negativa en EMA3 de 1H
    prices_inflection = [230.0 + (i * 0.5) for i in range(20)] + [239.0, 238.2, 237.5]
    df_1h_inflection = create_ohlc(prices_inflection)

    exit_res = evaluate_aduana_stocks_exit(
        position=pos,
        current_price=237.5,
        df_15m=df_1h_inflection,
        df_1h=df_1h_inflection
    )
    # Debe detectar el agotamiento de tendencia en 1H
    assert exit_res['should_close'] is True
    assert exit_res['pct_to_close'] in (50, 100)
