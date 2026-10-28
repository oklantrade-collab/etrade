"""
Unit Tests for ADUANA GAP RUNNER OPTIONS Engine
===============================================
Pruebas exhaustivas para:
- Clasificación de clase de activo y umbrales dinámicos de Gap.
- Ranking de velocidad por minuto para CALLs y PUTs.
- Validación de filtros MTF (1H Bollinger, RSI, EMA3/EMA9, 5m velas 1 y 2).
- Tranches 1, 2 y 3 (incluyendo HOD Breakout para CALLs y LOD Breakdown para PUTs).
- Selector inteligente de contratos (Delta, DTE, Liquidez, Sizing de Tranches).
- Defensivas ADUANA Opciones (Hard SL -35%, Stall Guard 20m, Trailing Tiers 2/3, Clímax RSI).
"""

import os
import sys
sys.path.append(os.path.abspath("backend"))

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

from app.options.aduana_gap_runner_options import (
    get_asset_class,
    get_min_gap_threshold,
    calculate_options_velocity_ranking,
    evaluate_options_gap_entry_tranches,
    evaluate_options_gap_aduana_exit
)
from app.options.opt_contract_picker import (
    select_best_option_contract,
    calculate_tranche_allocation
)
from app.options.opt_gap_aduana_defense import evaluate_opt_gap_defense


def _make_df(rows):
    return pd.DataFrame(rows)


def test_asset_class_and_gap_thresholds():
    """Valida la clasificación dinámica de activos y sus umbrales de gap mínimos."""
    assert get_asset_class("SPY") == "ETF"
    assert get_min_gap_threshold("SPY") == 0.60

    assert get_asset_class("NVDA") == "MEGA_CAP"
    assert get_min_gap_threshold("NVDA") == 1.20

    assert get_asset_class("COIN") == "HIGH_BETA"
    assert get_min_gap_threshold("COIN") == 3.00

    assert get_asset_class("IRON") == "SMALL_CAP"
    assert get_min_gap_threshold("IRON") == 5.00


def test_velocity_ranking_calls_and_puts():
    """Valida que el ranking de velocidad ordene correctamente por mayor aceleración."""
    df_slow = _make_df([
        {'open': 100.0, 'close': 100.2},
        {'open': 100.2, 'close': 100.5}   # +0.3 en 5m
    ])
    df_fast = _make_df([
        {'open': 100.0, 'close': 100.5},
        {'open': 100.5, 'close': 102.0}   # +1.5 en 5m (más rápido)
    ])
    df_drop_fast = _make_df([
        {'open': 100.0, 'close': 99.5},
        {'open': 99.5, 'close': 97.5}    # -2.0 en 5m (caída rápida)
    ])
    df_drop_slow = _make_df([
        {'open': 100.0, 'close': 99.8},
        {'open': 99.8, 'close': 99.3}    # -0.5 en 5m
    ])

    # 1. Ranking CALLs
    cands_call = [
        {'ticker': 'SLOW', 'df_5m': df_slow},
        {'ticker': 'FAST', 'df_5m': df_fast}
    ]
    ranked_call = calculate_options_velocity_ranking(cands_call, direction="CALL")
    assert ranked_call[0]['ticker'] == 'FAST'
    assert ranked_call[0]['velocity_rank'] == 1
    assert ranked_call[0]['rate_pct_per_min'] > ranked_call[1]['rate_pct_per_min']

    # 2. Ranking PUTs
    cands_put = [
        {'ticker': 'DROP_SLOW', 'df_5m': df_drop_slow},
        {'ticker': 'DROP_FAST', 'df_5m': df_drop_fast}
    ]
    ranked_put = calculate_options_velocity_ranking(cands_put, direction="PUT")
    assert ranked_put[0]['ticker'] == 'DROP_FAST'
    assert ranked_put[0]['velocity_rank'] == 1
    assert ranked_put[0]['rate_pct_per_min'] > ranked_put[1]['rate_pct_per_min']


def test_call_tranche_1_approves():
    """Valida que Tranche 1 de CALL se aprueba con vela 1 verde, vela 2 micro-gap y espacio 1H."""
    df_5m = _make_df([
        {'open': 100.0, 'high': 101.5, 'low': 99.8, 'close': 101.2, 'volume': 50000}, # Vela 1 verde
        {'open': 101.2, 'high': 102.0, 'low': 101.0, 'close': 101.8, 'volume': 60000}  # Vela 2 micro-gap
    ])
    # 1H con espacio alcista y EMA3 > EMA9
    h1_candles = [
        {'open': 95.0 + (i % 3) * 0.5, 'high': 98.0, 'low': 94.0, 'close': 95.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [95.8, 96.2, 96.5, 96.9, 97.2]:
        h1_candles.append({'open': p - 0.3, 'high': p + 0.8, 'low': p - 0.5, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    res = evaluate_options_gap_entry_tranches(
        ticker="NVDA",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=1.80, # Supera umbral de 1.20% para Mega-Cap
        direction="CALL",
        sipv_signal="BUY"
    )

    assert res['should_enter'] is True
    assert res['tranche_step'] == 1
    assert res['rule_code'] == 'OPT_GAP_TRANCHE_1_CALL'
    assert res['initial_sl_underlying'] is not None


def test_call_tranche_1_blocks_on_red_candle():
    """Valida bloqueo de CALL cuando la vela 1 de 5m fue roja."""
    df_5m = _make_df([
        {'open': 101.5, 'high': 101.8, 'low': 99.8, 'close': 100.0, 'volume': 50000}, # Vela 1 roja
        {'open': 100.0, 'high': 100.5, 'low': 99.5, 'close': 100.2, 'volume': 30000}
    ])
    h1_candles = [
        {'open': 95.0 + (i % 3) * 0.5, 'high': 98.0, 'low': 94.0, 'close': 95.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [95.8, 96.2, 96.5, 96.9, 97.2]:
        h1_candles.append({'open': p - 0.3, 'high': p + 0.8, 'low': p - 0.5, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    res = evaluate_options_gap_entry_tranches(
        ticker="NVDA",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=2.0,
        direction="CALL"
    )

    assert res['should_enter'] is False
    assert "Vela 1 de 5m fue roja" in res['reason']


def test_put_tranche_1_approves():
    """Valida que Tranche 1 de PUT se aprueba con vela 1 roja, vela 2 micro-gap bajista y espacio 1H."""
    df_5m = _make_df([
        {'open': 100.0, 'high': 100.2, 'low': 98.5, 'close': 98.8, 'volume': 50000}, # Vela 1 roja
        {'open': 98.7, 'high': 98.9, 'low': 97.5, 'close': 97.9, 'volume': 60000}    # Vela 2 micro-gap bajista
    ])
    # 1H con tendencia bajista (EMA3 < EMA9 y pendiente bajista, RSI ~44)
    h1_candles = [
        {'open': 103.0 + (i % 3) * 0.5, 'high': 106.0, 'low': 102.0, 'close': 103.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [103.8, 103.5, 103.2, 102.9, 102.6]:
        h1_candles.append({'open': p + 0.3, 'high': p + 0.5, 'low': p - 0.8, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    res = evaluate_options_gap_entry_tranches(
        ticker="COIN",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=-3.80, # Gap Down de -3.8% (supera umbral de -3.0% para High-Beta)
        direction="PUT",
        sipv_signal="SELL"
    )

    assert res['should_enter'] is True
    assert res['tranche_step'] == 1
    assert res['rule_code'] == 'OPT_GAP_TRANCHE_1_PUT'
    assert res['initial_sl_underlying'] is not None


def test_put_tranche_1_blocks_on_green_candle():
    """Valida bloqueo de PUT cuando la vela 1 de 5m fue verde (rebote)."""
    df_5m = _make_df([
        {'open': 98.0, 'high': 100.5, 'low': 97.8, 'close': 100.0, 'volume': 50000}, # Vela 1 verde
        {'open': 100.0, 'high': 100.4, 'low': 99.5, 'close': 99.8, 'volume': 30000}
    ])
    h1_candles = [
        {'open': 103.0 + (i % 3) * 0.5, 'high': 106.0, 'low': 102.0, 'close': 103.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [103.8, 103.5, 103.2, 102.9, 102.6]:
        h1_candles.append({'open': p + 0.3, 'high': p + 0.5, 'low': p - 0.8, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    res = evaluate_options_gap_entry_tranches(
        ticker="COIN",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=-4.0,
        direction="PUT"
    )

    assert res['should_enter'] is False
    assert "Vela 1 de 5m fue verde" in res['reason']


def test_call_tranche_2_approves_on_hod_breakout():
    """Valida Tranche 2 de CALL por ruptura del High of Day (HOD) en 5m con volumen."""
    df_5m = _make_df([
        {'open': 100.0, 'high': 101.0, 'low': 99.8, 'close': 100.5, 'volume': 20000},
        {'open': 100.5, 'high': 101.2, 'low': 100.2, 'close': 100.8, 'volume': 20000},
        {'open': 100.8, 'high': 102.5, 'low': 100.7, 'close': 102.2, 'volume': 50000} # Ruptura de HOD ($101.20)
    ])
    df_15m = _make_df([
        {'open': 100.0, 'high': 101.2, 'low': 99.8, 'close': 100.8, 'volume': 40000},
        {'open': 100.7, 'high': 102.5, 'low': 100.6, 'close': 102.2, 'volume': 50000}
    ])
    pos = {
        'id': 'pos-call-t2',
        'status': 'open',
        'reentry_count': 0,
        'avg_price': 100.5,
        'direction': 'CALL'
    }

    res = evaluate_options_gap_entry_tranches(
        ticker="NVDA",
        df_5m=df_5m,
        df_15m=df_15m,
        gap_pct=1.5,
        active_position=pos,
        direction="CALL"
    )

    assert res['should_enter'] is True
    assert res['tranche_step'] == 2
    assert res['rule_code'] in ('OPT_GAP_TRANCHE_2_CALL', 'OPT_GAP_TRANCHE_2_HOD')
    assert res['initial_sl_underlying'] == 100.5 # Breakeven


def test_put_tranche_2_approves_on_lod_breakdown():
    """Valida Tranche 2 de PUT por ruptura del Low of Day (LOD) en 5m con volumen."""
    df_5m = _make_df([
        {'open': 100.0, 'high': 100.2, 'low': 98.5, 'close': 99.0, 'volume': 20000},
        {'open': 99.0, 'high': 99.2, 'low': 98.2, 'close': 98.4, 'volume': 20000},
        {'open': 98.4, 'high': 98.5, 'low': 97.0, 'close': 97.2, 'volume': 50000} # Quiebre de LOD ($98.20)
    ])
    df_15m = _make_df([
        {'open': 100.0, 'high': 100.2, 'low': 98.2, 'close': 98.4, 'volume': 40000},
        {'open': 98.4, 'high': 98.5, 'low': 97.0, 'close': 97.2, 'volume': 50000}
    ])
    pos = {
        'id': 'pos-put-t2',
        'status': 'open',
        'reentry_count': 0,
        'avg_price': 99.0,
        'direction': 'PUT'
    }

    res = evaluate_options_gap_entry_tranches(
        ticker="COIN",
        df_5m=df_5m,
        df_15m=df_15m,
        gap_pct=-3.5,
        active_position=pos,
        direction="PUT"
    )

    assert res['should_enter'] is True
    assert res['tranche_step'] == 2
    assert res['rule_code'] in ('OPT_GAP_TRANCHE_2_PUT', 'OPT_GAP_TRANCHE_2_LOD')
    assert res['initial_sl_underlying'] == 99.0 # Breakeven


def test_tranche_allocation_sizing():
    """Valida la distribución de contratos enteros en tranches."""
    t1, t2, t3, model = calculate_tranche_allocation(6)
    assert model == "3_TRANCHES"
    assert t1 == 2 and t2 == 2 and t3 == 2

    t1, t2, t3, model = calculate_tranche_allocation(2)
    assert model == "2_TRANCHES"
    assert t1 == 1 and t2 == 1 and t3 == 0

    t1, t2, t3, model = calculate_tranche_allocation(1)
    assert model == "SINGLE"
    assert t1 == 1 and t2 == 0 and t3 == 0


def test_contract_picker_delta_and_liquidity():
    """Valida la selección del strike con Delta óptimo (~0.50) y spread estrecho."""
    today = date(2026, 10, 20)
    exp = today + timedelta(days=7)

    contracts = [
        # Opción 1: Muy OTM (Delta 0.20)
        {'conid': 101, 'right': 'C', 'strike': 120.0, 'expiry': exp.isoformat(),
         'bid': 0.40, 'ask': 0.45, 'delta': 0.20, 'open_interest': 500, 'volume': 100},
        # Opción 2: ATM Óptima (Delta 0.52, spread estrecho)
        {'conid': 102, 'right': 'C', 'strike': 100.0, 'expiry': exp.isoformat(),
         'bid': 3.10, 'ask': 3.20, 'delta': 0.52, 'open_interest': 1200, 'volume': 450},
        # Opción 3: Spread muy amplio (descartada)
        {'conid': 103, 'right': 'C', 'strike': 105.0, 'expiry': exp.isoformat(),
         'bid': 1.00, 'ask': 1.80, 'delta': 0.48, 'open_interest': 800, 'volume': 200}
    ]

    best, _ = select_best_option_contract(
        contracts=contracts,
        underlying_price=100.0,
        direction="CALL",
        budget_usd=1000.0,
        now_date=today
    )

    assert best is not None
    assert best.conid == 102
    assert best.strike == 100.0
    assert best.delta == 0.52
    assert best.target_total_contracts == 3 # $1000 / $315 = 3 contratos


def test_defense_hard_stop_loss_premium():
    """Valida Hard SL cuando la prima de la opción sufre una caída <= -35%."""
    pos = {
        'id': 'pos-sl',
        'avg_price': 4.00,
        'direction': 'CALL'
    }
    # Prima cae a $2.50 (-37.5% de pérdida)
    res = evaluate_opt_gap_defense(
        position=pos,
        current_underlying_price=100.0,
        current_option_premium=2.50
    )
    assert res['should_exit'] is True
    assert res['exit_type'] == 'hard_stop'
    assert res['rule_code'] == 'OPT_GAP_HARD_SL_PREM'


def test_defense_stall_guard():
    """Valida Stall Guard cuando la posición lleva 25 min sin avanzar y pierde -18% por Theta."""
    pos = {
        'id': 'pos-stall',
        'avg_price': 3.00,
        'reentry_count': 0,
        'direction': 'CALL'
    }
    res = evaluate_opt_gap_defense(
        position=pos,
        current_underlying_price=100.0,
        current_option_premium=2.45, # -18.3%
        position_age_minutes=25.0
    )
    assert res['should_exit'] is True
    assert res['exit_type'] == 'stall_guard'
    assert res['rule_code'] == 'OPT_GAP_STALL_GUARD'


def test_defense_trailing_tier2_profit():
    """Valida Trailing Ratchet Tier 2 (piso garantizado de +15% cuando la prima ganó >= +25%)."""
    pos = {
        'id': 'pos-tier2',
        'avg_price': 2.00,
        'highest_premium_seen': 2.60, # Ganó +30% pico
        'direction': 'CALL'
    }
    # La prima retrocede a $2.25 (piso de +15% es $2.30)
    res = evaluate_opt_gap_defense(
        position=pos,
        current_underlying_price=102.0,
        current_option_premium=2.25
    )
    assert res['should_exit'] is True
    assert res['exit_type'] == 'trailing_stop'
    assert res['rule_code'] == 'OPT_GAP_TRAIL_TIER2'


def test_defense_trailing_tier3_hyper_profit():
    """Valida Trailing Ratchet Tier 3 (blindaje del 70% del pico cuando la prima subió >= +50%)."""
    # Compra a $2.00, subió a $3.60 (+80% pico)
    # Ganancia pico = $1.60. 70% blindado = $1.60 * 0.70 = $1.12. Nivel blindado = $2.00 + $1.12 = $3.12
    pos = {
        'id': 'pos-tier3',
        'avg_price': 2.00,
        'highest_premium_seen': 3.60,
        'direction': 'CALL'
    }
    # La prima retrocede a $3.05 (por debajo de $3.12)
    res = evaluate_opt_gap_defense(
        position=pos,
        current_underlying_price=105.0,
        current_option_premium=3.05
    )
    assert res['should_exit'] is True
    assert res['exit_type'] == 'trailing_stop'
    assert res['rule_code'] == 'OPT_GAP_TRAIL_TIER3'


def test_defense_tp_climax_total():
    """Valida Take Profit Clímax Total cuando RSI 1H >= 85 (CALL) o <= 15 (PUT)."""
    # 1. Clímax CALL
    df_1h_overbought = _make_df([{'close': 100.0 + i*2.0} for i in range(25)])
    pos_call = {'id': 'pos-climax-call', 'avg_price': 2.00, 'direction': 'CALL'}
    res_call = evaluate_opt_gap_defense(
        position=pos_call,
        current_underlying_price=150.0,
        current_option_premium=5.00,
        df_1h=df_1h_overbought
    )
    assert res_call['should_exit'] is True
    assert res_call['rule_code'] == 'OPT_GAP_TP_CLIMAX'

    # 2. Clímax PUT
    df_1h_oversold = _make_df([{'close': 100.0 - i*2.0} for i in range(25)])
    pos_put = {'id': 'pos-climax-put', 'avg_price': 2.00, 'direction': 'PUT'}
    res_put = evaluate_opt_gap_defense(
        position=pos_put,
        current_underlying_price=50.0,
        current_option_premium=6.00,
        df_1h=df_1h_oversold
    )
    assert res_put['should_exit'] is True
    assert res_put['rule_code'] == 'OPT_GAP_TP_CLIMAX'


# ==============================================================================
# TESTS DE PRIORIZACIÓN DE COMPRA EN OPPORTUNITIES (GAP RUNNERS)
# ==============================================================================

def test_is_gap_runner_opportunity_detection():
    """Valida la detección de Gap Runner tanto en candidatas directas como por subyacente."""
    from app.options.score import is_gap_runner_opportunity

    # 1. Candidata marcada directamente
    c1 = {'id': 1, 'is_gap_runner': True, 'gap_type': 'OPEN_GAP_UP', 'gap_pct': 4.5}
    is_r, gtype, gpct = is_gap_runner_opportunity(c1)
    assert is_r is True
    assert gtype == 'OPEN_GAP_UP'
    assert gpct == 4.5

    # 2. Subyacente Mega-Cap con Gap Up >= 1.2%
    c2 = {'id': 2, 'direction': 'CALL'}
    u2 = {'symbol': 'NVDA', 'catalyst_meta': {'c1_gap': {'gap_pct': 1.8}}}
    is_r2, gtype2, gpct2 = is_gap_runner_opportunity(c2, u2)
    assert is_r2 is True
    assert gtype2 == 'OPEN_GAP_UP'

    # 3. Subyacente ETF con Gap Down <= -0.6%
    c3 = {'id': 3, 'direction': 'PUT'}
    u3 = {'symbol': 'SPY', 'catalyst_meta': {'c1_gap': {'gap_pct': -0.9}}}
    is_r3, gtype3, gpct3 = is_gap_runner_opportunity(c3, u3)
    assert is_r3 is True
    assert gtype3 == 'OPEN_GAP_DOWN'

    # 4. Subyacente que NO supera umbral (ej. NVDA con +0.5% < 1.2%)
    c4 = {'id': 4, 'direction': 'CALL'}
    u4 = {'symbol': 'NVDA', 'catalyst_meta': {'c1_gap': {'gap_pct': 0.5}}}
    is_r4, _, _ = is_gap_runner_opportunity(c4, u4)
    assert is_r4 is False


def test_score_boost_gap_runner_call_and_put():
    """Valida que un Gap Runner reciba un Score Boost institucional de +25 puntos."""
    from app.options.score import score_candidate
    eff = {'w_expectancy': 30, 'w_apex_signal': 20, 'w_liquidity': 20, 'w_risk': 15, 'w_iv_greeks': 10, 'w_context': 5}
    legs = [{'bid': 2.0, 'ask': 2.1, 'iv': 0.35, 'delta': 0.50, 'side': 'buy'}]

    # Candidata regular (sin gap runner)
    from unittest.mock import patch
    cand_reg = {
        'id': 10, 'strategy_type': 'long_call', 'direction': 'CALL',
        'ev_ratio': 0.20, 'ev_view_net': 15.0, 'max_loss_contract': 100.0,
        'legs': legs
    }
    und_reg = {'symbol': 'AMZN', 'direction': 'CALL', 'apex_score': 60.0}
    with patch('app.core.structural_regime_engine.evaluate_structural_regime') as mock_reg:
        mock_reg.return_value = {'is_dead_stock': False, 'setup_bonus': 0.0, 'regime_code': 'BULL_TREND', 'setup_name': 'NORMAL', 'setup_label': 'NORMAL', 'key_levels_1d': {}}
        res_reg = score_candidate(cand_reg, und_reg, eff)
        assert res_reg['score_breakdown']['is_gap_runner'] is False
        assert res_reg['score_breakdown']['gap_runner_boost'] == 0.0

        # Misma candidata pero calificada como OPEN GAP UP Runner
        cand_gap = dict(cand_reg)
        cand_gap['id'] = 11
        cand_gap['is_gap_runner'] = True
        cand_gap['gap_type'] = 'OPEN_GAP_UP'
        cand_gap['gap_pct'] = 3.5
        res_gap = score_candidate(cand_gap, und_reg, eff)

        assert res_gap['score_breakdown']['is_gap_runner'] is True
        assert res_gap['score_breakdown']['gap_runner_boost'] == 25.0
        # El score final debe ser mayor por el boost de 25 pts (hasta 100 máx)
        assert res_gap['score'] >= res_reg['score'] + 15.0


def test_portfolio_selector_gap_runner_first_priority():
    """Valida que select_portfolio asigne prioridad absoluta a Gap Runners frente a candidatas comunes."""
    from app.options.portfolio_selector import select_portfolio
    eff = {'max_open_risk_usd': 150.0, 'max_risk_per_trade_usd': 100.0, 'max_daily_selections': 3, 'min_score': 50.0}

    # 3 candidatas elegibles
    # Cand 1: Spread común con score 80
    c1 = {'id': 101, 'underlying_id': 1, 'symbol': 'AAPL', 'direction': 'bullish', 'score': 80.0, 'max_loss_total': 80.0, 'eligibility_status': 'eligible'}
    # Cand 2: Gap Runner con score 75
    c2 = {'id': 102, 'underlying_id': 2, 'symbol': 'NVDA', 'direction': 'bullish', 'score': 75.0, 'max_loss_total': 70.0, 'is_gap_runner': True, 'gap_type': 'OPEN_GAP_UP', 'eligibility_status': 'eligible'}
    # Cand 3: Spread común con score 78
    c3 = {'id': 103, 'underlying_id': 3, 'symbol': 'MSFT', 'direction': 'bullish', 'score': 78.0, 'max_loss_total': 60.0, 'eligibility_status': 'eligible'}

    res = select_portfolio([c1, c2, c3], existing_positions=[], eff=eff)
    selected = res.selected
    assert len(selected) >= 1
    # La candidata #1 seleccionada DEBE ser el Gap Runner (NVDA id 102), a pesar de que c1 tenía score 80
    assert selected[0]['id'] == 102
    assert selected[0]['symbol'] == 'NVDA'
    assert selected[0]['is_gap_runner'] is True


def test_call_tranche_1_approves_on_dip_and_rip():
    """Valida que CALL Tranche 1 se apruebe con el patrón Dip & Rip (sacudida roja + 2 verdes)."""
    df_5m = _make_df([
        {'open': 100.0, 'high': 100.2, 'low': 98.5, 'close': 98.8, 'volume': 50000},  # V1 Roja (Dip)
        {'open': 98.8, 'high': 99.0, 'low': 98.0, 'close': 98.2, 'volume': 45000},   # V2 Roja (Dip Low = 98.0)
        {'open': 98.2, 'high': 99.6, 'low': 98.1, 'close': 99.5, 'volume': 75000},   # V3 Verde (Giro)
        {'open': 99.5, 'high': 101.2, 'low': 99.4, 'close': 100.8, 'volume': 90000}, # V4 Verde (Confirmación)
    ])
    h1_candles = [
        {'open': 95.0 + (i % 3) * 0.5, 'high': 98.0, 'low': 94.0, 'close': 95.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [95.8, 96.2, 96.5, 96.9, 97.2]:
        h1_candles.append({'open': p - 0.3, 'high': p + 0.8, 'low': p - 0.5, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches

    res = evaluate_options_gap_entry_tranches(
        ticker="NVDA",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=3.0,
        direction="CALL",
        sipv_signal="BUY"
    )

    assert res['should_enter'] is True
    assert res['tranche_step'] == 1
    assert res['rule_code'] == 'OPT_GAP_DIP_AND_RIP_CALL'
    assert res['initial_sl_underlying'] <= 98.0
    assert "Dip & Rip Tranche 1 aprobado" in res['reason']


def test_put_tranche_1_approves_on_pop_and_drop():
    """Valida que PUT Tranche 1 se apruebe con el patrón Pop & Drop (rebote verde + 2 rojas)."""
    df_5m = _make_df([
        {'open': 98.0, 'high': 100.0, 'low': 97.8, 'close': 99.8, 'volume': 50000},   # V1 Verde (Pop)
        {'open': 99.8, 'high': 101.5, 'low': 99.6, 'close': 101.2, 'volume': 45000},  # V2 Verde (Pop High = 101.5)
        {'open': 101.2, 'high': 101.3, 'low': 99.8, 'close': 100.0, 'volume': 80000},  # V3 Roja (Rechazo)
        {'open': 100.0, 'high': 100.1, 'low': 98.2, 'close': 98.5, 'volume': 95000},   # V4 Roja (Confirmación)
    ])
    h1_candles = [
        {'open': 103.0 + (i % 3) * 0.5, 'high': 106.0, 'low': 102.0, 'close': 103.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [103.8, 103.5, 103.2, 102.9, 102.6]:
        h1_candles.append({'open': p + 0.3, 'high': p + 0.5, 'low': p - 0.8, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches

    res = evaluate_options_gap_entry_tranches(
        ticker="COIN",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=-5.0,
        direction="PUT",
        sipv_signal="SELL"
    )

    assert res['should_enter'] is True
    assert res['tranche_step'] == 1
    assert res['rule_code'] == 'OPT_GAP_POP_AND_DROP_PUT'
    assert res['initial_sl_underlying'] >= 101.5
    assert "Pop & Drop Tranche 1 aprobado" in res['reason']


def test_call_dip_and_rip_blocks_if_pierces_prev_close():
    """Valida bloqueo de CALL cuando la sacudida rompe por debajo del cierre previo (caída libre >3%)."""
    # cur_p = 100.0, gap_pct = 5.0 -> est_prev_close = 95.23
    # Sacudida cae a 90.0 (perfora 95.23 por más del 5%)
    df_5m = _make_df([
        {'open': 100.0, 'high': 100.1, 'low': 90.0, 'close': 90.5, 'volume': 50000},
        {'open': 90.5, 'high': 91.0, 'low': 89.8, 'close': 90.2, 'volume': 45000},
        {'open': 90.2, 'high': 93.0, 'low': 90.1, 'close': 92.5, 'volume': 75000},
        {'open': 92.5, 'high': 95.0, 'low': 92.4, 'close': 94.5, 'volume': 90000},
    ])
    h1_candles = [
        {'open': 95.0 + (i % 3) * 0.5, 'high': 98.0, 'low': 94.0, 'close': 95.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [95.8, 96.2, 96.5, 96.9, 97.2]:
        h1_candles.append({'open': p - 0.3, 'high': p + 0.8, 'low': p - 0.5, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches

    res = evaluate_options_gap_entry_tranches(
        ticker="NVDA",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=5.0,
        direction="CALL",
        sipv_signal="BUY"
    )

    assert res['should_enter'] is False
    assert "perforó cierre previo" in res['reason']


def test_put_pop_and_drop_blocks_if_pierces_prev_close():
    """Valida bloqueo de PUT cuando el rebote supera el cierre previo por más del 3%."""
    # cur_p = 95.0, gap_pct = -5.0 -> est_prev_close = 100.0
    # Rebote sube a 104.5 (supera 100.0 por 4.5% > 3%)
    df_5m = _make_df([
        {'open': 95.0, 'high': 104.0, 'low': 94.8, 'close': 103.5, 'volume': 50000},
        {'open': 103.5, 'high': 104.5, 'low': 102.0, 'close': 104.2, 'volume': 45000},
        {'open': 104.2, 'high': 104.3, 'low': 99.0, 'close': 99.5, 'volume': 75000},
        {'open': 99.5, 'high': 99.6, 'low': 97.0, 'close': 97.5, 'volume': 90000},
    ])
    h1_candles = [
        {'open': 103.0 + (i % 3) * 0.5, 'high': 106.0, 'low': 102.0, 'close': 103.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [103.8, 103.5, 103.2, 102.9, 102.6]:
        h1_candles.append({'open': p + 0.3, 'high': p + 0.5, 'low': p - 0.8, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches

    res = evaluate_options_gap_entry_tranches(
        ticker="COIN",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=-5.0,
        direction="PUT",
        sipv_signal="SELL"
    )

    assert res['should_enter'] is False
    assert "rebote perforó cierre previo" in res['reason']


def test_call_orb_15m_breakout_approves():
    """Valida ORB 15m Breakout para CALLs tras consolidación inicial."""
    # Primeros 15m (velas 1, 2, 3) consolidan entre 100.0 y 103.0
    # Vela 4 (09:45-09:50) rompe sobre 103.0 cerrando en 104.5
    df_5m = _make_df([
        {'open': 100.0, 'high': 103.0, 'low': 99.5, 'close': 102.0, 'volume': 50000},
        {'open': 102.0, 'high': 102.8, 'low': 101.0, 'close': 101.5, 'volume': 40000},
        {'open': 101.5, 'high': 102.0, 'low': 101.0, 'close': 101.2, 'volume': 45000}, # Roja
        {'open': 101.2, 'high': 104.8, 'low': 101.0, 'close': 104.5, 'volume': 80000}, # Breakout ORB sobre 103.0
    ])
    h1_candles = [
        {'open': 95.0 + (i % 3) * 0.5, 'high': 108.0, 'low': 94.0, 'close': 95.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [95.8, 96.2, 96.5, 96.9, 97.2]:
        h1_candles.append({'open': p - 0.3, 'high': p + 0.8, 'low': p - 0.5, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches

    res = evaluate_options_gap_entry_tranches(
        ticker="NVDA",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=3.0,
        direction="CALL",
        sipv_signal="BUY"
    )

    assert res['should_enter'] is True
    assert res['rule_code'] == 'OPT_GAP_ORB_CALL'
    assert res['initial_sl_underlying'] <= 101.5


def test_put_orb_15m_breakdown_approves():
    """Valida ORB 15m Breakdown para PUTs tras consolidación bajista."""
    # Primeros 15m consolidan entre 98.0 y 96.0
    # Vela 4 rompe el piso cerrando en 94.5
    df_5m = _make_df([
        {'open': 98.0, 'high': 98.5, 'low': 96.0, 'close': 96.8, 'volume': 50000},
        {'open': 96.8, 'high': 97.2, 'low': 96.2, 'close': 96.5, 'volume': 40000},
        {'open': 96.5, 'high': 97.0, 'low': 96.1, 'close': 96.8, 'volume': 45000}, # Verde
        {'open': 96.8, 'high': 96.9, 'low': 94.2, 'close': 94.5, 'volume': 85000}, # Breakdown ORB bajo 96.0
    ])
    h1_candles = [
        {'open': 103.0 + (i % 3) * 0.5, 'high': 106.0, 'low': 102.0, 'close': 103.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [103.8, 103.5, 103.2, 102.9, 102.6]:
        h1_candles.append({'open': p + 0.3, 'high': p + 0.5, 'low': p - 0.8, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches

    res = evaluate_options_gap_entry_tranches(
        ticker="COIN",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=-4.0,
        direction="PUT",
        sipv_signal="SELL"
    )

    assert res['should_enter'] is True
    assert res['rule_code'] == 'OPT_GAP_ORB_PUT'
    assert res['initial_sl_underlying'] >= 97.0


def test_call_vwap_reload_approves():
    """Valida entrada CALL con rebote y confirmación en VWAP post-frenesí inicial (10:00+)."""
    # 6 velas: velas 1-3 abren fuerte, velas 4-5 corrigen a VWAP (~103), vela 6 rebota verde
    df_5m = _make_df([
        {'open': 100.0, 'high': 104.0, 'low': 99.8, 'close': 103.5, 'volume': 100000},
        {'open': 103.5, 'high': 105.0, 'low': 103.0, 'close': 104.8, 'volume': 80000},
        {'open': 104.8, 'high': 105.2, 'low': 103.8, 'close': 104.0, 'volume': 60000},
        {'open': 104.0, 'high': 104.2, 'low': 103.0, 'close': 103.2, 'volume': 50000},
        {'open': 103.2, 'high': 103.5, 'low': 102.8, 'close': 103.0, 'volume': 45000},
        {'open': 103.0, 'high': 104.5, 'low': 102.9, 'close': 104.2, 'volume': 75000}, # Rebote verde sobre VWAP
    ])
    h1_candles = [
        {'open': 95.0 + (i % 3) * 0.5, 'high': 108.0, 'low': 94.0, 'close': 95.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [95.8, 96.2, 96.5, 96.9, 97.2]:
        h1_candles.append({'open': p - 0.3, 'high': p + 0.8, 'low': p - 0.5, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches

    res = evaluate_options_gap_entry_tranches(
        ticker="NVDA",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=3.0,
        direction="CALL",
        sipv_signal="BUY"
    )

    assert res['should_enter'] is True
    assert res['rule_code'] in ('OPT_GAP_VWAP_CALL', 'OPT_GAP_DIP_AND_RIP_CALL')


def test_put_vwap_rejection_approves():
    """Valida entrada PUT con rechazo en VWAP tras rebote alcista fallido (10:00+)."""
    # 6 velas: velas 1-3 caen fuerte, velas 4-5 rebotan hacia VWAP (~97), vela 6 rechaza roja
    df_5m = _make_df([
        {'open': 100.0, 'high': 100.2, 'low': 96.0, 'close': 96.5, 'volume': 100000},
        {'open': 96.5, 'high': 97.0, 'low': 95.0, 'close': 95.2, 'volume': 80000},
        {'open': 95.2, 'high': 96.2, 'low': 95.0, 'close': 96.0, 'volume': 60000},
        {'open': 96.0, 'high': 97.2, 'low': 95.8, 'close': 97.0, 'volume': 50000},
        {'open': 97.0, 'high': 97.4, 'low': 96.8, 'close': 97.1, 'volume': 45000},
        {'open': 97.1, 'high': 97.3, 'low': 95.5, 'close': 95.8, 'volume': 75000}, # Rechazo rojo bajo VWAP
    ])
    h1_candles = [
        {'open': 103.0 + (i % 3) * 0.5, 'high': 106.0, 'low': 102.0, 'close': 103.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [103.8, 103.5, 103.2, 102.9, 102.6]:
        h1_candles.append({'open': p + 0.3, 'high': p + 0.5, 'low': p - 0.8, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches

    res = evaluate_options_gap_entry_tranches(
        ticker="COIN",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=-4.0,
        direction="PUT",
        sipv_signal="SELL"
    )

    assert res['should_enter'] is True
    assert res['rule_code'] in ('OPT_GAP_VWAP_PUT', 'OPT_GAP_POP_AND_DROP_PUT')


def test_put_market_gate_blocks_when_spy_bullish_above_vwap():
    """Valida que el Market Gate bloquee PUTs cuando SPY cotiza alcista sobre su VWAP."""
    df_5m = _make_df([
        {'open': 100.0, 'high': 100.2, 'low': 98.0, 'close': 98.5, 'volume': 50000},
        {'open': 98.5, 'high': 98.6, 'low': 96.5, 'close': 97.0, 'volume': 60000}
    ])
    h1_candles = [
        {'open': 103.0 + (i % 3) * 0.5, 'high': 106.0, 'low': 102.0, 'close': 103.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [103.8, 103.5, 103.2, 102.9, 102.6]:
        h1_candles.append({'open': p + 0.3, 'high': p + 0.5, 'low': p - 0.8, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    # SPY 5m cotizando en 505.0 claramente sobre su VWAP (~501.0)
    df_spy = _make_df([
        {'open': 500.0, 'high': 502.0, 'low': 499.5, 'close': 501.5, 'volume': 1000000},
        {'open': 501.5, 'high': 505.5, 'low': 501.2, 'close': 505.0, 'volume': 1200000}
    ])

    from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches

    res = evaluate_options_gap_entry_tranches(
        ticker="COIN",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=-3.80,
        direction="PUT",
        sipv_signal="SELL",
        df_market_ref=df_spy,
        market_ref_symbol="SPY"
    )

    assert res['should_enter'] is False
    assert "Market Gate" in res['reason']
    assert "cotiza sobre su VWAP" in res['reason']


def test_put_blocked_when_underlying_trades_above_vwap():
    """Valida bloqueo de PUT cuando el propio subyacente cotiza sobre su VWAP (absorción compradora)."""
    # Vela 1 cae de 100 a 96 con volumen 50k (VWAP ~96.5)
    # Vela 2 y 3 rebotan hasta 98 con volumen 150k (VWAP sube a ~97.3, precio actual 98.0 > VWAP)
    df_5m = _make_df([
        {'open': 100.0, 'high': 100.2, 'low': 95.8, 'close': 96.0, 'volume': 50000},
        {'open': 96.0, 'high': 97.5, 'low': 95.9, 'close': 97.2, 'volume': 60000},
        {'open': 97.2, 'high': 98.5, 'low': 97.0, 'close': 98.0, 'volume': 90000}
    ])
    h1_candles = [
        {'open': 103.0 + (i % 3) * 0.5, 'high': 106.0, 'low': 102.0, 'close': 103.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [103.8, 103.5, 103.2, 102.9, 102.6]:
        h1_candles.append({'open': p + 0.3, 'high': p + 0.5, 'low': p - 0.8, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches

    res = evaluate_options_gap_entry_tranches(
        ticker="COIN",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=-4.0,
        direction="PUT",
        sipv_signal="SELL"
    )

    assert res['should_enter'] is False
    assert "cotiza sobre su VWAP" in res['reason']


def test_put_blocked_in_opening_when_candle_2_fails_to_break_low():
    """Valida bloqueo en apertura directa cuando vela 2 se estanca y no quebra el mínimo de vela 1."""
    # Vela 1 Low = 98.0. Vela 2 Close = 98.4 (no perfora 98.0)
    df_5m = _make_df([
        {'open': 100.0, 'high': 100.2, 'low': 98.0, 'close': 98.2, 'volume': 50000},
        {'open': 98.2, 'high': 98.6, 'low': 98.1, 'close': 98.4, 'volume': 40000}
    ])
    h1_candles = [
        {'open': 103.0 + (i % 3) * 0.5, 'high': 106.0, 'low': 102.0, 'close': 103.5 + ((i + 1) % 3) * 0.5, 'volume': 100000}
        for i in range(20)
    ]
    for p in [103.8, 103.5, 103.2, 102.9, 102.6]:
        h1_candles.append({'open': p + 0.3, 'high': p + 0.5, 'low': p - 0.8, 'close': p, 'volume': 120000})
    df_1h = _make_df(h1_candles)

    from app.options.aduana_gap_runner_options import evaluate_options_gap_entry_tranches

    res = evaluate_options_gap_entry_tranches(
        ticker="COIN",
        df_5m=df_5m,
        df_1h=df_1h,
        gap_pct=-4.0,
        direction="PUT",
        sipv_signal="SELL"
    )

    assert res['should_enter'] is False
    assert "no perforó el mínimo de Vela 1" in res['reason']


def test_put_exit_defense_when_underlying_reclaims_vwap():
    """Valida salida defensiva anticipada cuando el subyacente recupera su VWAP al alza."""
    # 5m: vela 1 y 2 bajistas, vela 3 rompe con fuerza sobre VWAP ($102.50 vs VWAP $101.00)
    df_5m = _make_df([
        {'open': 102.0, 'high': 102.2, 'low': 99.8, 'close': 100.0, 'volume': 50000},
        {'open': 100.0, 'high': 100.5, 'low': 99.5, 'close': 100.2, 'volume': 40000},
        {'open': 100.2, 'high': 102.8, 'low': 100.0, 'close': 102.5, 'volume': 90000}
    ])
    pos = {
        'id': 'pos-put-1',
        'avg_price': 3.00,
        'highest_premium_seen': 3.10,
        'direction': 'PUT'
    }
    from app.options.aduana_gap_runner_options import evaluate_options_gap_aduana_exit

    # Prima cae a $2.70 (-10.0%, no es -35% aún, pero subyacente recuperó VWAP)
    res = evaluate_options_gap_aduana_exit(
        position=pos,
        current_underlying_price=102.50,
        current_option_premium=2.70,
        df_5m=df_5m
    )

    assert res['should_exit'] is True
    assert res['rule_code'] == 'OPT_GAP_PUT_EXIT_VWAP'
    assert "recuperó su VWAP" in res['reason']


def test_put_exit_breakeven_shield():
    """Valida que un PUT que ganó >= +15% blinde el precio de entrada (Breakeven)."""
    pos = {
        'id': 'pos-put-be',
        'avg_price': 2.00,
        'highest_premium_seen': 2.36, # Ganó +18% pico
        'direction': 'PUT'
    }
    from app.options.aduana_gap_runner_options import evaluate_options_gap_aduana_exit

    # Prima retrocede a $2.01 (en el umbral de entrada)
    res = evaluate_options_gap_aduana_exit(
        position=pos,
        current_underlying_price=98.0,
        current_option_premium=2.01
    )

    assert res['should_exit'] is True
    assert res['rule_code'] in ('OPT_GAP_PUT_BREAKEVEN', 'OPT_GAP_BE_LOCK_PLUS_1PCT')
    assert "Breakeven" in res['reason']



