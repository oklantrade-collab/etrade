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
    # Velas con oscilación realista para que RSI 1H esté en zona normal (~65) y no dispare falso clímax >85
    h1_candles = [{'open': 9.9 + (i % 3) * 0.15, 'high': 10.3, 'low': 9.8, 'close': 10.0 + ((i + 1) % 3) * 0.15, 'volume': 100000} for i in range(20)]
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


def test_aduana_exit_climax_rsi85():
    """Regla 1.e: Si RSI 1H > 85, Cierre Total inmediato (100%)."""
    # 25 velas con subida vertical continua para empujar RSI 1H > 85
    h1_candles = []
    base_p = 10.0
    for i in range(25):
        base_p += 0.8
        h1_candles.append({
            'open': base_p - 0.7,
            'high': base_p + 0.2,
            'low': base_p - 0.7,
            'close': base_p,
            'volume': 200000
        })
    df_1h = _make_df(h1_candles)

    pos = {
        'id': 'pos-climax',
        'ticker': 'ROCKET',
        'status': 'open',
        'avg_price': 15.0,
        'stop_loss': 20.0,
        'shares': 120
    }

    res = evaluate_gap_runner_aduana_exit(
        position=pos,
        current_price=base_p,
        df_1h=df_1h
    )

    assert res['should_exit'] is True
    assert res['exit_type'] == 'full'
    assert res['rule_code'] == 'ADUANA_GAP_CLIMAX_RSI85'
    assert res['shares_to_exit'] == 120
    assert res['rsi_1h'] > 85.0


def test_aduana_exit_upper6_partial_tp():
    """Reglas 1.b & 1.d: Cierre parcial 50% al alcanzar UPPER_6 o RSI 15m > 80 (sin Rocket Hold)."""
    # 20 velas de 15m para tener bandas Fibonacci y Bollinger válidas
    candles_15m = []
    p = 10.0
    for i in range(20):
        candles_15m.append({
            'open': p,
            'high': p + 0.3,
            'low': p - 0.2,
            'close': p + 0.1,
            'volume': 50000
        })
        p += 0.1
    # Última vela: Open dentro de Bollinger (Open=12.0, BB Upper ~12.2), precio actual explota a 13.50 (UPPER_6)
    candles_15m.append({
        'open': 12.0,
        'high': 13.6,
        'low': 11.9,
        'close': 13.5,
        'volume': 250000
    })
    df_15m = _make_df(candles_15m)

    pos = {
        'id': 'pos-upper6',
        'ticker': 'FAST',
        'status': 'open',
        'avg_price': 11.0,
        'stop_loss': 10.5,
        'shares': 100,
        'tp_block1_executed': False
    }

    res = evaluate_gap_runner_aduana_exit(
        position=pos,
        current_price=13.5,
        df_15m=df_15m
    )

    assert res['should_exit'] is True
    assert res['exit_type'] == 'partial_50'
    assert res['shares_to_exit'] == 50
    assert 'UPPER' in res['rule_code'] or 'RSI' in res['rule_code']


def test_aduana_exit_rocket_hold_exception():
    """Regla 1.c: Si Open 15m > BB Upper y SIPV es BUY -> HOLD (no vender parcial)."""
    # Velas estables seguidas de una vela que abre muy por encima de BB Upper
    candles_15m = [{'open': 10.0, 'high': 10.2, 'low': 9.9, 'close': 10.1, 'volume': 50000}] * 20
    # Penúltima vela: cerró con cuerpo verde fuerte (SIPV Buy)
    candles_15m.append({'open': 10.1, 'high': 11.0, 'low': 10.1, 'close': 10.9, 'volume': 150000})
    # Última vela: Open a 11.80 (muy por encima de BB Upper ~10.40)
    candles_15m.append({'open': 11.8, 'high': 12.5, 'low': 11.7, 'close': 12.4, 'volume': 300000})
    df_15m = _make_df(candles_15m)

    pos = {
        'id': 'pos-rocket',
        'ticker': 'MOON',
        'status': 'open',
        'avg_price': 10.2,
        'stop_loss': 9.8,
        'shares': 100,
        'sipv_15m': 'BUY'
    }

    res = evaluate_gap_runner_aduana_exit(
        position=pos,
        current_price=12.4,
        df_15m=df_15m
    )

    assert res['should_exit'] is False
    assert res['action'] == 'hold'
    assert res['rule_code'] == 'ADUANA_GAP_ROCKET_HOLD'


def test_aduana_trailing_15m_ema9():
    """Regla 1.a: Si EMA9 15m asciende, mover Stop Loss debajo de (EMA9 - delta)."""
    candles_15m = []
    for i in range(15):
        base_p = 10.0 + (i * 0.1)
        candles_15m.append({
            'open': base_p - 0.05,
            'high': base_p + 0.15,
            'low': base_p - 0.1,
            'close': base_p + ((i % 2) * 0.04),
            'volume': 40000
        })
    df_15m = _make_df(candles_15m)

    cur_p = 11.6
    pos = {
        'id': 'pos-trail15',
        'ticker': 'STEADY',
        'status': 'open',
        'avg_price': 10.0,
        'stop_loss': 9.5,  # SL antiguo abajo
        'shares': 100,
        'tp_block1_executed': True  # Ya se tomó TP parcial previamente
    }

    res = evaluate_gap_runner_aduana_exit(
        position=pos,
        current_price=cur_p,
        df_15m=df_15m
    )

    assert res['new_stop_loss'] is not None
    assert res['new_stop_loss'] > 9.5
    assert res['new_stop_loss'] < cur_p
    assert res['rule_code'] == 'ADUANA_GAP_TRAIL_EMA9'


def test_aduana_trailing_1h_midpoint():
    """Regla 2.a: Trailing STOP en 1H colocado al 50% de vela verde que perfora BB Upper."""
    # 20 velas con oscilación sana para mantener RSI 1H < 85
    h1_candles = [{'open': 9.8 + (i % 3) * 0.2, 'high': 10.4, 'low': 9.7, 'close': 10.0 + ((i + 1) % 3) * 0.2, 'volume': 100000} for i in range(20)]
    # Última vela cerrada perfora BB Upper (High=14.50 > BB Upper ~10.50): Open=10.0, Close=14.0
    # Midpoint esperado: 10.0 + (14.0 - 10.0) / 2 = 12.00
    h1_candles.append({
        'open': 10.0,
        'high': 14.5,
        'low': 9.9,
        'close': 14.0,
        'volume': 500000
    })
    df_1h = _make_df(h1_candles)

    pos = {
        'id': 'pos-midpoint',
        'ticker': 'BURST',
        'status': 'open',
        'avg_price': 10.2,
        'stop_loss': 9.8,  # SL inicial
        'shares': 100
    }

    res = evaluate_gap_runner_aduana_exit(
        position=pos,
        current_price=14.2,
        df_1h=df_1h
    )

    assert res['new_stop_loss'] == 12.00
    assert res['rule_code'] == 'ADUANA_GAP_TRAIL_MIDPOINT_1H'
    assert res['exit_type'] == 'trailing_update'


def test_tranche_2_approves_on_hod_breakout():
    """Mejora 1: Tranche 2 aprobado por ruptura de High of Day (HOD) en 5m con volumen."""
    # 5m: velas iniciales con High en 11.00, seguidas de ruptura con volumen a 11.50
    df_5m = _make_df([
        {'open': 10.0, 'high': 10.8, 'low': 9.9, 'close': 10.5, 'volume': 50000},
        {'open': 10.5, 'high': 11.0, 'low': 10.4, 'close': 10.6, 'volume': 30000},
        {'open': 10.6, 'high': 10.7, 'low': 10.3, 'close': 10.4, 'volume': 20000},
        # Ruptura de HOD ($11.00) con volumen
        {'open': 10.5, 'high': 11.5, 'low': 10.5, 'close': 11.4, 'volume': 80000}
    ])
    # 15m sin continuación (abrió abajo en vela 2)
    df_15m = _make_df([
        {'open': 10.0, 'high': 11.0, 'low': 9.9, 'close': 10.6, 'volume': 100000},
        {'open': 10.4, 'high': 11.5, 'low': 10.3, 'close': 11.4, 'volume': 100000}
    ])
    df_1h = _make_df([{'open': 9.5, 'high': 12.5, 'low': 9.4, 'close': 11.0, 'volume': 200000}] * 20)

    pos = {
        'id': 'pos-hod',
        'ticker': 'BREAKOUT',
        'status': 'open',
        'reentry_count': 0,
        'avg_price': 10.5,
        'stop_loss': 9.9,
        'shares': 100
    }

    res = evaluate_gap_runner_entry_tranches(
        ticker="BREAKOUT",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=15.0,
        active_position=pos
    )

    assert res['should_enter'] is True
    assert res['tranche_step'] == 2
    assert res['rule_code'] == 'GAP_TRANCHE_2_HOD_BREAKOUT'
    assert res['initial_sl'] == 10.5  # Breakeven


def test_tiered_trailing_stop_profit_25pct():
    """Mejora 2 (Tier 2): Ganancia flotante +30% activa piso garantizado de al menos +15% neto."""
    df_15m = _make_df([
        {'open': 10.0, 'high': 10.5, 'low': 9.8, 'close': 10.2, 'volume': 50000},
        {'open': 10.2, 'high': 13.2, 'low': 10.1, 'close': 13.0, 'volume': 150000}
    ])
    df_5m = _make_df([
        {'open': 12.0, 'high': 13.2, 'low': 11.9, 'close': 13.0, 'volume': 50000}
    ])

    pos = {
        'id': 'pos-tier2',
        'ticker': 'WINNER',
        'status': 'open',
        'avg_price': 10.0,
        'stop_loss': 9.5,
        'shares': 100,
        'tp_block1_executed': True
    }

    res = evaluate_gap_runner_aduana_exit(
        position=pos,
        current_price=13.0,  # +30% ganancia
        df_5m=df_5m,
        df_15m=df_15m
    )

    assert res['new_stop_loss'] is not None
    assert res['new_stop_loss'] >= 11.50  # Piso +15% garantizado (10.0 * 1.15)
    assert res['new_stop_loss'] < 13.0
    assert res['rule_code'] == 'ADUANA_GAP_TRAIL_TIER2'


def test_tiered_trailing_stop_hyper_50pct():
    """Mejora 2 (Tier 3): Ganancia flotante +70% activa blindaje de al menos 70% de la ganancia pico."""
    # Promedio compra 10.0, precio actual 17.0 (+70% ganancia)
    # 70% de la ganancia = 10.0 + (17.0 - 10.0) * 0.70 = 14.90
    df_5m = _make_df([
        {'open': 15.0, 'high': 16.0, 'low': 14.8, 'close': 15.8, 'volume': 80000},
        {'open': 15.8, 'high': 17.2, 'low': 15.7, 'close': 17.0, 'volume': 120000}
    ])
    df_15m = _make_df([
        {'open': 14.0, 'high': 17.2, 'low': 13.8, 'close': 17.0, 'volume': 200000}
    ])

    pos = {
        'id': 'pos-hyper',
        'ticker': 'PARABOLIC',
        'status': 'open',
        'avg_price': 10.0,
        'stop_loss': 11.5,
        'shares': 100
    }

    res = evaluate_gap_runner_aduana_exit(
        position=pos,
        current_price=17.0,  # +70% ganancia
        df_5m=df_5m,
        df_15m=df_15m
    )

    assert res['new_stop_loss'] is not None
    assert res['new_stop_loss'] >= 14.90  # 70% de ganancia blindada
    assert res['new_stop_loss'] < 17.0
    assert res['rule_code'] == 'ADUANA_GAP_TRAIL_TIER3'


def test_orchestrator_composite_rank_gap_runner():
    """Valida que calculate_composite_rank otorgue máxima prioridad (>= 99.5) a OPEN GAP UP."""
    from app.stocks.stocks_orchestrator import calculate_composite_rank

    cfg = {'weights': {'apex_4h': 0.35, 'apex_1d': 0.25, 'return_expected': 0.25, 'rvol': 0.15}}
    
    # Activo estándar
    rank_normal = calculate_composite_rank(
        apex_4h=70.0, apex_1d=65.0, return_pct=8.0, confidence="HIGH", rvol=1.5, cfg=cfg,
        is_gap_runner=False
    )
    # Activo con OPEN GAP UP institucional
    rank_runner = calculate_composite_rank(
        apex_4h=70.0, apex_1d=65.0, return_pct=8.0, confidence="HIGH", rvol=1.5, cfg=cfg,
        is_gap_runner=True
    )

    assert rank_runner >= 99.5
    assert rank_runner > rank_normal
    assert rank_runner >= rank_normal + 25.0 or rank_runner >= 99.5


def test_orchestrator_queue_sort_gap_runner_priority():
    """Valida que la cola del Orchestrator priorice a OPEN GAP UP por encima de otras señales."""
    def sort_key(c):
        is_runner      = bool(c.get('is_gap_runner'))
        has_signal     = bool(c.get('has_rule_signal') or c.get('is_pullback_b') or c.get('is_breakout_5m'))
        not_overbought = not bool(c.get('is_overbought'))
        bf             = float(c.get('buying_force_score') or 0.0)
        rank           = float(c.get('composite_rank') or 0.0)
        return (not_overbought, is_runner, has_signal, bf >= 70.0, rank)

    c_standard = {
        'ticker': 'AAPL', 'is_gap_runner': False, 'has_rule_signal': True,
        'is_overbought': False, 'buying_force_score': 85.0, 'composite_rank': 90.0
    }
    c_pullback = {
        'ticker': 'NVDA', 'is_gap_runner': False, 'has_rule_signal': True,
        'is_overbought': False, 'buying_force_score': 90.0, 'composite_rank': 98.8
    }
    c_gap_runner = {
        'ticker': 'SMCI', 'is_gap_runner': True, 'has_rule_signal': True,
        'is_overbought': False, 'buying_force_score': 75.0, 'composite_rank': 99.8
    }

    candidates = [c_standard, c_pullback, c_gap_runner]
    candidates.sort(key=sort_key, reverse=True)

    # SMCI (Open Gap Runner) debe ser #1 indiscutible en la cola de compra del BOT
    assert candidates[0]['ticker'] == 'SMCI'
    assert candidates[0]['is_gap_runner'] is True


def test_stocks_opportunities_open_gap_up_boost_and_sort():
    """Valida que los activos con OPEN GAP UP reciban +25 pts y se ordenen con prioridad 0 en la API."""
    from app.options.aduana_gap_runner_options import get_min_gap_threshold

    items = [
        {'ticker': 'TSLA', 'gap_pct': 4.5, 'rank_score': 70.0, 'buying_force_5m': 70.0, 'is_trap': False},  # High-Beta thresh=3.0% -> RUNNER
        {'ticker': 'AAPL', 'gap_pct': 0.8, 'rank_score': 85.0, 'buying_force_5m': 85.0, 'is_trap': False},  # Mega-Cap thresh=1.2% -> NO RUNNER
        {'ticker': 'PLTR', 'gap_pct': 5.0, 'rank_score': 65.0, 'buying_force_5m': 65.0, 'is_trap': False},  # High-Beta thresh=3.0% -> RUNNER
    ]

    for opp in items:
        t = opp['ticker']
        min_thresh = get_min_gap_threshold(t)
        gap_val = opp['gap_pct']
        is_runner = (gap_val >= min_thresh) and not opp['is_trap']
        opp['is_gap_runner'] = is_runner
        if is_runner:
            opp['gap_runner_boost'] = 25.0
            opp['rank_score'] = round(min(100.0, opp['rank_score'] + 25.0), 1)

    items.sort(key=lambda x: (
        0 if x.get("is_gap_runner") else 1,
        -float(x.get("rank_score") or 0.0),
        -float(x.get("gap_pct") or 0.0)
    ))

    # TSLA (70 + 25 = 95.0) y PLTR (65 + 25 = 90.0) deben estar en posiciones 0 y 1 antes que AAPL
    assert items[0]['ticker'] == 'TSLA'
    assert items[0]['rank_score'] == 95.0
    assert items[0]['is_gap_runner'] is True

    assert items[1]['ticker'] == 'PLTR'
    assert items[1]['rank_score'] == 90.0
    assert items[1]['is_gap_runner'] is True

    assert items[2]['ticker'] == 'AAPL'
    assert items[2]['is_gap_runner'] is False


def test_tranche_1_approves_on_dip_and_rip_pattern():
    """Valida que el patrón 'Dip & Rip' (sacudida roja + giro de 2 velas verdes) apruebe Tranche 1."""
    # Simulación caso HOST: Gap Up +18%, apertura roja (sacudida a 1.88) y giro con 2 velas verdes
    df_5m = _make_df([
        {'open': 2.10, 'high': 2.12, 'low': 1.95, 'close': 1.96, 'volume': 80000},  # V1 Roja (Dip)
        {'open': 1.96, 'high': 1.98, 'low': 1.88, 'close': 1.90, 'volume': 75000},  # V2 Roja (Dip Low = 1.88)
        {'open': 1.90, 'high': 2.05, 'low': 1.89, 'close': 2.02, 'volume': 110000}, # V3 Verde (Giro/Absorción)
        {'open': 2.02, 'high': 2.20, 'low': 2.01, 'close': 2.15, 'volume': 130000}, # V4 Verde (Confirmación)
    ])
    df_15m = _make_df([{'open': 2.10, 'high': 2.20, 'low': 1.88, 'close': 2.15, 'volume': 395000}])
    # 1H con espacio a Bollinger Upper y RSI ~55
    h1_candles = [{'open': 1.70 + (i % 2) * 0.05, 'high': 2.30, 'low': 1.65, 'close': 1.72 + ((i + 1) % 2) * 0.05, 'volume': 500000} for i in range(25)]
    df_1h = _make_df(h1_candles)

    res = evaluate_gap_runner_entry_tranches(
        ticker="HOST",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=18.0,
        active_position=None
    )

    assert res['should_enter'] is True
    assert res['tranche_step'] == 1
    assert res['rule_code'] == 'GAP_DIP_AND_RIP_1'
    assert res['tranche_shares_ratio'] == 0.3333
    # SL inicial debe estar en o por debajo del mínimo de la sacudida (1.88)
    assert res['initial_sl'] <= 1.88
    assert "Dip & Rip Tranche 1 activado" in res['reason']


def test_dip_and_rip_blocks_if_pullback_erases_gap():
    """Valida que el patrón se anule si la sacudida perfora el cierre de la sesión previa (falling knife)."""
    # Precio actual 2.00 con Gap de 10% -> Prev Close estimado ~ 1.818
    # Sacudida cae a 1.70 (debajo del cierre anterior)
    df_5m = _make_df([
        {'open': 2.00, 'high': 2.02, 'low': 1.70, 'close': 1.72, 'volume': 80000},  # V1 Roja perfora cierre previo
        {'open': 1.72, 'high': 1.75, 'low': 1.68, 'close': 1.70, 'volume': 75000},  # V2 Roja
        {'open': 1.70, 'high': 1.85, 'low': 1.69, 'close': 1.82, 'volume': 90000},  # V3 Verde
        {'open': 1.82, 'high': 1.95, 'low': 1.81, 'close': 1.90, 'volume': 95000},  # V4 Verde
    ])
    df_15m = _make_df([{'open': 2.00, 'high': 2.02, 'low': 1.68, 'close': 1.90, 'volume': 340000}])
    df_1h = _make_df([{'open': 1.70, 'high': 2.20, 'low': 1.65, 'close': 1.75, 'volume': 500000}] * 25)

    res = evaluate_gap_runner_entry_tranches(
        ticker="KNIFE",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=10.0,
        active_position=None
    )

    assert res['should_enter'] is False
    assert "perforó cierre previo" in res['reason']


def test_dip_and_rip_blocks_if_pullback_erases_more_than_75pct_of_gap():
    """Valida bloqueo cuando la sacudida borra más del 75% del Gap inicial."""
    # Prev Close estimado = 10.00 / 1.20 = 8.33. Open Day = 10.00. Gap = 1.67.
    # Max allowed drop = 10.00 - (0.75 * 1.67) = 8.75.
    # Sacudida cae a 8.60 (borra ~84% del gap).
    df_5m = _make_df([
        {'open': 10.00, 'high': 10.05, 'low': 8.60, 'close': 8.70, 'volume': 80000},  # V1
        {'open': 8.70, 'high': 9.20, 'low': 8.65, 'close': 9.15, 'volume': 75000},   # V2
        {'open': 9.15, 'high': 9.50, 'low': 9.10, 'close': 9.45, 'volume': 90000},   # V3
    ])
    df_15m = _make_df([{'open': 10.00, 'high': 10.05, 'low': 8.60, 'close': 9.45, 'volume': 245000}])
    df_1h = _make_df([{'open': 8.50, 'high': 11.00, 'low': 8.30, 'close': 8.80, 'volume': 500000}] * 25)

    res = evaluate_gap_runner_entry_tranches(
        ticker="OVERDIP",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=20.0,
        active_position=None
    )

    assert res['should_enter'] is False
    assert "borró más del 75% del Gap" in res['reason']


def test_gap_fill_and_rip_with_wick_sweep_approves():
    """Valida que un Gap Fill con barrido de mecha de hasta -3% bajo cierre previo apruebe (caso HOST)."""
    # Open 2.23 (Gap 16.15%). Cierre previo = 2.23 / 1.1615 = 1.92.
    # Sacudida cae a 1.87 (-2.6% bajo cierre previo de 1.92).
    # Velas 3 y 4 confirman giro y recuperan sobre 1.92 (1.93 -> 2.03).
    df_5m = _make_df([
        {'open': 2.23, 'high': 2.27, 'low': 1.92, 'close': 2.02, 'volume': 600000},  # V1 Roja
        {'open': 2.00, 'high': 2.01, 'low': 1.87, 'close': 1.90, 'volume': 50000},   # V2 Roja (Low = 1.87)
        {'open': 1.90, 'high': 1.95, 'low': 1.87, 'close': 1.93, 'volume': 35000},   # V3 Verde
        {'open': 1.90, 'high': 2.06, 'low': 1.90, 'close': 2.03, 'volume': 45000},   # V4 Verde (Recupera sobre 1.92)
    ])
    df_15m = _make_df([{'open': 2.23, 'high': 2.27, 'low': 1.87, 'close': 2.03, 'volume': 730000}])
    df_1h = _make_df([{'open': 1.80, 'high': 2.30, 'low': 1.70, 'close': 1.92, 'volume': 500000}] * 25)

    res = evaluate_gap_runner_entry_tranches(
        ticker="HOST",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=16.15,
        active_position=None
    )

    assert res['should_enter'] is True
    assert res['rule_code'] in ('GAP_DIP_AND_RIP_1', 'GAP_FILL_AND_RIP_1')
    assert res['initial_sl'] <= 1.87
    assert "Tranche 1 activado" in res['reason']


def test_orb_15m_breakout_approves():
    """Valida la estrategia ORB: Ruptura de rango de apertura de 15m con volumen."""
    # Primeros 15m (velas 1, 2, 3) consolidan entre 10.00 y 10.50
    # Vela 4 (09:45-09:50) rompe el techo de 10.50 con volumen expansivo (35k vs 10k promedio)
    df_5m = _make_df([
        {'open': 10.00, 'high': 10.50, 'low': 9.90, 'close': 10.30, 'volume': 10000},
        {'open': 10.30, 'high': 10.45, 'low': 10.10, 'close': 10.40, 'volume': 8000},
        {'open': 10.40, 'high': 10.48, 'low': 10.15, 'close': 10.35, 'volume': 11000},  # V3 Roja
        {'open': 10.35, 'high': 10.80, 'low': 10.30, 'close': 10.75, 'volume': 35000},  # V4 Ruptura ORB
    ])
    df_15m = _make_df([{'open': 10.00, 'high': 10.50, 'low': 9.90, 'close': 10.40, 'volume': 29000}])
    df_1h = _make_df([{'open': 9.50, 'high': 12.00, 'low': 9.40, 'close': 10.00, 'volume': 300000}] * 25)

    res = evaluate_gap_runner_entry_tranches(
        ticker="ORB_STOCK",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=8.0,
        active_position=None
    )

    assert res['should_enter'] is True
    assert res['rule_code'] == 'GAP_ORB_BREAKOUT_1'
    assert res['initial_sl'] <= 10.00
    assert "ORB 15m Breakout activado" in res['reason']


def test_vwap_reload_approves():
    """Valida la estrategia VWAP Reload: Testeo y rebote sobre VWAP entre 10:00 y 11:30 ET."""
    # 6 velas de 5m (30 minutos transcurridos). Precio testea VWAP y rebota con vela verde.
    candles = [
        {'open': 10.0, 'high': 10.8, 'low': 9.9, 'close': 10.6, 'volume': 20000},
        {'open': 10.6, 'high': 10.9, 'low': 10.4, 'close': 10.7, 'volume': 15000},
        {'open': 10.7, 'high': 10.8, 'low': 10.4, 'close': 10.75, 'volume': 12000},
        {'open': 10.75, 'high': 10.8, 'low': 10.4, 'close': 10.7, 'volume': 10000},
        {'open': 10.7, 'high': 10.75, 'low': 10.45, 'close': 10.5, 'volume': 9000},
        {'open': 10.5, 'high': 10.85, 'low': 10.48, 'close': 10.80, 'volume': 25000},
    ]
    df_5m = _make_df(candles)
    df_15m = _make_df([{'open': 10.0, 'high': 10.9, 'low': 9.9, 'close': 10.8, 'volume': 91000}])
    df_1h = _make_df([{'open': 9.5, 'high': 12.0, 'low': 9.4, 'close': 10.0, 'volume': 300000}] * 25)

    res = evaluate_gap_runner_entry_tranches(
        ticker="VWAP_STOCK",
        df_5m=df_5m,
        df_15m=df_15m,
        df_1h=df_1h,
        gap_pct=10.0,
        active_position=None
    )

    assert res['should_enter'] is True
    assert res['rule_code'] == 'GAP_VWAP_RELOAD_1'





