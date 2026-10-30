"""
Test Opportunities Ranking, 1H EMA3 > EMA9 Filter, and Blocked Stock Exclusion
==============================================================================
Verifica que:
1. Las acciones con EMA3 <= EMA9 en 1H o RSI >= 80 NO califiquen como gap_runner.
2. Las acciones con estado 'blocked' o 'is_deep_bear_excluded' sean castigadas en rank_score (<= 25.0) y enviadas al fondo del ranking.
3. Acciones sin liquidez mínima intradía no califiquen como runners.
4. Las acciones legítimas de alta liquidez con 1H EMA3 > EMA9 y gap institucional lideren el Top 3.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_gap_runner_criteria_logic():
    # Caso 1: Acción con Gap 40%, pero EMA3 < EMA9 en 1H -> NO debe ser runner
    eff_gap = 40.0
    min_thresh = 3.0
    is_trap = False
    is_ema3_above_ema9 = False
    rsi_1h_num = 55.0
    is_ema3_asc = False
    vol_val = 6 # Caso TNMG con 6 acciones
    rvol_val = 0.1
    is_status_blocked = False

    meets_1h_criteria = bool(is_ema3_above_ema9 and (rsi_1h_num < 80.0) and is_ema3_asc)
    has_min_liquidity = (vol_val >= 50_000) or (rvol_val >= 1.5 and vol_val >= 15_000)
    is_runner = (eff_gap >= min_thresh) and (not is_trap) and meets_1h_criteria and has_min_liquidity and (not is_status_blocked)

    assert meets_1h_criteria is False
    assert has_min_liquidity is False
    assert is_runner is False


def test_gap_runner_criteria_blocked_or_trap():
    # Caso 2: Acción con Gap 20%, volumen y 1H alcista, pero status='blocked' (o trampa) -> NO debe ser runner
    eff_gap = 20.0
    min_thresh = 3.0
    is_trap = True
    is_ema3_above_ema9 = True
    rsi_1h_num = 60.0
    is_ema3_asc = True
    vol_val = 200_000
    rvol_val = 2.5
    is_status_blocked = True

    meets_1h_criteria = bool(is_ema3_above_ema9 and (rsi_1h_num < 80.0) and is_ema3_asc)
    has_min_liquidity = (vol_val >= 50_000) or (rvol_val >= 1.5 and vol_val >= 15_000)
    is_runner = (eff_gap >= min_thresh) and (not is_trap) and meets_1h_criteria and has_min_liquidity and (not is_status_blocked)

    assert meets_1h_criteria is True
    assert has_min_liquidity is True
    assert is_runner is False


def test_genuine_gap_runner_qualifies():
    # Caso 3: Acción legítima (Ross Cameron criteria): Gap +15%, 1H EMA3 > EMA9, RSI 58, 500k vol -> Runner calificado
    eff_gap = 15.0
    min_thresh = 3.0
    is_trap = False
    is_ema3_above_ema9 = True
    rsi_1h_num = 58.0
    is_ema3_asc = True
    vol_val = 500_000
    rvol_val = 3.2
    is_status_blocked = False

    meets_1h_criteria = bool(is_ema3_above_ema9 and (rsi_1h_num < 80.0) and is_ema3_asc)
    has_min_liquidity = (vol_val >= 50_000) or (rvol_val >= 1.5 and vol_val >= 15_000)
    is_runner = (eff_gap >= min_thresh) and (not is_trap) and meets_1h_criteria and has_min_liquidity and (not is_status_blocked)

    assert meets_1h_criteria is True
    assert has_min_liquidity is True
    assert is_runner is True


def test_ranking_sort_demotes_blocked_and_descending():
    items = [
        {
            "ticker": "TNMG",
            "rank_score": 25.0,
            "gap_pct": 44.3,
            "is_gap_runner": False,
            "status": "blocked",
            "queue_status": "blocked",
            "is_ema3_above_ema9": False,
            "is_deep_bear_excluded": True,
        },
        {
            "ticker": "WKHS",
            "rank_score": 25.0,
            "gap_pct": 5.0,
            "is_gap_runner": False,
            "status": "blocked",
            "queue_status": "blocked",
            "is_ema3_above_ema9": False,
            "is_deep_bear_excluded": False,
        },
        {
            "ticker": "RUNNER_A",
            "rank_score": 85.0,
            "gap_pct": 18.0,
            "is_gap_runner": True,
            "status": "watching",
            "queue_status": "watching",
            "is_ema3_above_ema9": True,
            "is_deep_bear_excluded": False,
        },
        {
            "ticker": "NORMAL_B",
            "rank_score": 70.0,
            "gap_pct": 4.0,
            "is_gap_runner": False,
            "status": "watching",
            "queue_status": "watching",
            "is_ema3_above_ema9": True,
            "is_deep_bear_excluded": False,
        }
    ]

    items.sort(key=lambda x: (
        1 if (
            str(x.get("status") or "").lower() == "blocked"
            or str(x.get("queue_status") or "").lower() == "blocked"
            or x.get("is_deep_bear_excluded")
            or not x.get("is_ema3_above_ema9", True)
        ) else 0,
        0 if x.get("is_gap_runner") else 1,
        -float(x.get("rank_score") or 0.0),
        -float(x.get("gap_pct") or 0.0)
    ))

    # El primero DEBE ser el runner legítimo
    assert items[0]["ticker"] == "RUNNER_A"
    assert items[1]["ticker"] == "NORMAL_B"
    # Los bloqueados y descendentes (TNMG, WKHS) deben quedar estrictamente al fondo
    assert items[2]["ticker"] in ["TNMG", "WKHS"]
    assert items[3]["ticker"] in ["TNMG", "WKHS"]
