"""
Test Suite: ADUANA OPEN GAP RUNNER ENGINE (STOCKS)
==================================================
Valida el funcionamiento matemático y operativo de:
1. Ranking dinámico de velocidad en 5 minutos (%/min).
2. Entradas progresivas en 3 Tranches (1/3, 2/3, 3/3).
3. Bloqueo de trampas (Vela 1 roja en 5m, sin espacio en Bollinger 1H).
4. Supervisión y salidas ADUANA (Aplanamiento de EMA3 1H, Compresión sobre BB Upper 1H).
"""

import os
import sys
sys.path.append(os.path.abspath("backend"))

import pytest
import pandas as pd
import numpy as np
from app.stocks.aduana_gap_runner_engine import (
    calculate_gap_velocity_ranking,
    evaluate_gap_runner_entry_tranches,
    evaluate_gap_runner_aduana_exit
)


def _make_df(candles: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col not in df.columns:
            df[col] = 10.0
    return df


def test_velocity_ranking_orders_by_rate_per_min():
    """Valida que los candidatos se ordenen de mayor a menor tasa por minuto."""
    # Candidato A: de 10.0 a 10.50 en 5m (+5.0% -> 1.0%/min)
    df_a = _make_df([
        {'open': 9.8, 'high': 10.1, 'low': 9.7, 'close': 10.0, 'volume': 50000},
        {'open': 10.0, 'high': 10.6, 'low': 10.0, 'close': 10.5, 'volume': 80000}
    ])
    # Candidato B: de 20.0 a 20.20 en 5m (+1.0% -> 0.2%/min)
    df_b = _make_df([
        {'open': 19.8, 'high': 20.1, 'low': 19.7, 'close': 20.0, 'volume': 60000},
        {'open': 20.0, 'high': 20.3, 'low': 19.9, 'close': 20.2, 'volume': 70000}
    ])
    # Candidato C: de 5.0 a 5.40 en 5m (+8.0% -> 1.6%/min)
    df_c = _make_df([
        {'open': 4.9, 'high': 5.1, 'low': 4.8, 'close': 5.0, 'volume': 90000},
        {'open': 5.0, 'high': 5.5, 'low': 5.0, 'close': 5.4, 'volume': 120000}
    ])

    candidates = [
        {'ticker': 'AAA', 'df_5m': df_a, 'gap_pct': 15.0},
        {'ticker': 'BBB', 'df_5m': df_b, 'gap_pct': 10.0},
        {'ticker': 'CCC', 'df_5m': df_c, 'gap_pct': 25.0}
    ]

    ranked = calculate_gap_velocity_ranking(candidates)

    assert len(ranked) == 3
    # El primero debe ser CCC (+1.6%/min), segundo AAA (+1.0%/min), tercero BBB (+0.2%/min)
    assert ranked[0]['ticker'] == 'CCC'
    assert ranked[0]['rate_per_min'] == 1.6
    assert ranked[1]['ticker'] == 'AAA'
    assert ranked[1]['rate_per_min'] == 1.0
    assert ranked[2]['ticker'] == 'BBB'
    assert ranked[2]['rate_per_min'] == 0.2


def test_tranche_1_approves_when_candle_1_green_and_candle_2_micro_gap():
    """Tranche 1/3: Vela 1 verde 5m + Vela 2 micro-gap alcista + espacio 1H."""
    # 5m: Vela 1 (10.0 -> 10.40 verde), Vela 2 (10.45 -> 10.70 verde)
    df_5m = _make_df([
        {'open': 10.0, 'high': 10.5, 'low': 9.9, 'close': 10.4, 'volume': 40000},
        {'open': 10.45, 'high': 10.8, 'low': 10.4, 'close': 10.7, 'volume': 60000}
    ])
    df_15m = _make_df([
        {'open': 10.0, 'high': 10.8, 'low': 9.9, 'close': 10.7, 'volume': 100000}
    ])
    # 1H con espacio a Bollinger Upper (Precio 10.70, BB Upper en 12.50, RSI ~52)
    h1_candles = [{'open': 9.5 + (i % 2) * 0.2, 'high': 10.8, 'low': 9.2, 'close': 9.6 + ((i + 1) % 2) * 0.2, 'volume': 200000} for i in range(25)]
    df_1h = _make_df(h1_candles)

    res = evaluate_gap_runner_entry_tranches(
        ticker="RUNNER",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=28.0,
        active_position=None
    )

    assert res['should_enter'] is True
    assert res['tranche_step'] == 1
    assert res['rule_code'] == 'GAP_TRANCHE_1'
    assert res['tranche_shares_ratio'] == 0.3333
    assert res['initial_sl'] == 9.9  # Low de vela 1 5m


def test_tranche_1_blocks_when_candle_1_red():
    """Trampa Gap & Crap: Vela 1 roja (Close <= Open) se rechaza de inmediato."""
    # Vela 1: Open 10.50, Close 10.10 (Roja bajista)
    df_5m = _make_df([
        {'open': 10.5, 'high': 10.6, 'low': 10.0, 'close': 10.1, 'volume': 80000},
        {'open': 10.1, 'high': 10.3, 'low': 9.9, 'close': 10.2, 'volume': 30000}
    ])
    df_15m = _make_df([{'open': 10.5, 'high': 10.6, 'low': 9.9, 'close': 10.2, 'volume': 110000}])
    df_1h = _make_df([{'open': 9.5, 'high': 11.0, 'low': 9.4, 'close': 10.2, 'volume': 200000}] * 25)

    res = evaluate_gap_runner_entry_tranches(
        ticker="TRAP",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=35.0,
        active_position=None
    )

    assert res['should_enter'] is False
    assert "no es alcista" in res['reason']


def test_tranche_2_approves_on_second_15m_candle():
    """Tranche 2/3: Si ya tiene Tranche 1, entra en la 2da vela de 15m y sube SL a Breakeven."""
    df_5m = _make_df([{'open': 10.0, 'high': 10.5, 'low': 9.9, 'close': 10.4, 'volume': 40000}] * 6)
    # 15m: Vela 1 (10.0 -> 10.40), Vela 2 (10.42 -> 10.80)
    df_15m = _make_df([
        {'open': 10.0, 'high': 10.5, 'low': 9.9, 'close': 10.4, 'volume': 120000},
        {'open': 10.42, 'high': 10.9, 'low': 10.4, 'close': 10.8, 'volume': 150000}
    ])
    df_1h = _make_df([{'open': 9.5, 'high': 12.0, 'low': 9.4, 'close': 10.8, 'volume': 300000}] * 25)

    active_pos = {
        'id': 'pos-123',
        'ticker': 'RUNNER',
        'status': 'open',
        'reentry_count': 0,
        'avg_price': 10.40,
        'stop_loss': 9.90,
        'shares': 100
    }

    res = evaluate_gap_runner_entry_tranches(
        ticker="RUNNER",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=30.0,
        active_position=active_pos
    )

    assert res['should_enter'] is True
    assert res['tranche_step'] == 2
    assert res['rule_code'] == 'GAP_TRANCHE_2'
    assert res['initial_sl'] == 10.40  # Breakeven


def test_aduana_exit_on_ema3_1h_slope_flattening():
    """Salida Defensiva ADUANA: Si la pendiente de EMA3 1H se vuelve plana/negativa y precio pierde EMA3."""
    # Precios 1H descendentes en las últimas velas
    h1_candles = [{'open': 10.0, 'high': 10.5, 'low': 9.8, 'close': 10.0, 'volume': 100000}] * 20
    # Agregamos velas donde el precio se desploma de 10.50 a 9.90
    h1_candles.append({'open': 10.4, 'high': 10.6, 'low': 10.2, 'close': 10.5, 'volume': 100000})
    h1_candles.append({'open': 10.5, 'high': 10.5, 'low': 10.0, 'close': 10.1, 'volume': 100000})
    h1_candles.append({'open': 10.1, 'high': 10.1, 'low': 9.8, 'close': 9.9, 'volume': 100000})
    df_1h = _make_df(h1_candles)

    pos = {
        'id': 'pos-456',
        'ticker': 'FLAT',
        'status': 'open',
        'avg_price': 10.20,
        'stop_loss': 9.50,
        'shares': 100
    }

    res = evaluate_gap_runner_aduana_exit(
        position=pos,
        current_price=9.85,
        df_1h=df_1h
    )

    assert res['should_exit'] is True
    assert res['rule_code'] == 'ADUANA_GAP_EXIT_SLOPE'
    assert res['exit_type'] == 'full'


def test_aduana_exit_on_bb_upper_range_compression():
    """Toma de Ganancias ADUANA: Vela 1H perfora BB Upper y luego el rango se comprime fuertemente."""
    h1_candles = [{'open': 10.0, 'high': 10.2, 'low': 9.9, 'close': 10.1, 'volume': 100000}] * 20
    # Vela penúltima: perfora fuertemente BB Upper con rango amplio (High 12.0, Low 10.2, Rango = 1.80)
    h1_candles.append({'open': 10.3, 'high': 12.0, 'low': 10.2, 'close': 11.8, 'volume': 500000})
    # Vela actual: comprimida en el techo (High 12.1, Low 11.6, Rango = 0.50 < 0.65 * 1.80)
    h1_candles.append({'open': 11.8, 'high': 12.1, 'low': 11.6, 'close': 11.7, 'volume': 150000})
    df_1h = _make_df(h1_candles)

    pos = {
        'id': 'pos-789',
        'ticker': 'BOOM',
        'status': 'open',
        'avg_price': 10.40,
        'stop_loss': 10.0,
        'shares': 100
    }

    res = evaluate_gap_runner_aduana_exit(
        position=pos,
        current_price=11.75,
        df_1h=df_1h
    )

    assert res['should_exit'] is True
    assert res['rule_code'] == 'ADUANA_GAP_EXIT_COMPRESSION'
    assert res['exit_type'] == 'partial_50'
    assert res['shares_to_exit'] == 50
    assert res['new_stop_loss'] == 10.20  # Low de la vela 1H previa
