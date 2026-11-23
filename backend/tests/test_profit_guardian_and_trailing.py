"""
Unit tests for Profit Guardian & Ross Cameron Trailing Stop Overhaul:
1. `profit_guardian.evaluate_option_profit_ratchet` continuous tiers (no +5% spread trap, no 5%..25% gap)
2. `exit_engine.evaluate_technical_rules_and_stops` evaluates `tp_peak_profit_ratchet` even when 15m BB is expanding
3. `micro_pullback_engine` dynamic trailing stop ratchets `stop_loss` on `highest_price_reached`
4. `broker_sync.is_option_closing_pending` expires stale >120s closing requests even if DB order stayed submitted
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_profit_guardian_no_premature_trap_under_12pct():
    from app.options.profit_guardian import evaluate_option_profit_ratchet

    # Caso real INTC #1772: pico +7.7%, cae a +1% -> NO debe disparar BE lock prematuro
    res = evaluate_option_profit_ratchet(
        entry_premium=2.3452,
        current_premium=2.35,
        highest_premium_seen=2.5262,  # +7.7%
    )
    assert res["should_exit"] is False
    assert res["floor_pct"] == 0.0


def test_profit_guardian_continuous_tiers():
    from app.options.profit_guardian import evaluate_option_profit_ratchet

    # Curva continua +10% .. +24.9% (10%->2%, 25%->15%): pico +14% -> piso +5.47% ($2.1094)
    r1 = evaluate_option_profit_ratchet(entry_premium=2.00, current_premium=2.10, highest_premium_seen=2.28)
    assert r1["should_exit"] is True
    assert r1["floor_pct"] == 5.47
    assert r1["rule_code"] == "OPT_GAP_BE_LOCK_PLUS_1PCT"

    # Pico +20% -> piso +10.67% ($2.2134)
    r2 = evaluate_option_profit_ratchet(entry_premium=2.00, current_premium=2.20, highest_premium_seen=2.40)
    assert r2["should_exit"] is True
    assert r2["floor_pct"] == 10.67

    # Curva continua +25% .. +49.9% (25%->15%, 50%->37.5%): pico +30% -> piso +19.5% ($2.39)
    r3 = evaluate_option_profit_ratchet(entry_premium=2.00, current_premium=2.38, highest_premium_seen=2.60)
    assert r3["should_exit"] is True
    assert r3["floor_pct"] == 19.5
    assert r3["rule_code"] == "OPT_GAP_TRAIL_TIER2"

    # Pico +40% -> piso +28.5% ($2.57)
    r4 = evaluate_option_profit_ratchet(entry_premium=2.00, current_premium=2.55, highest_premium_seen=2.80)
    assert r4["should_exit"] is True
    assert r4["floor_pct"] == 28.5
    assert r4["rule_code"] == "OPT_GAP_TRAIL_TIER2"

    # Tier 3 (>= +50%): protege 75% del pico (+80% -> +60%)
    r5 = evaluate_option_profit_ratchet(entry_premium=2.00, current_premium=3.15, highest_premium_seen=3.60)
    assert r5["should_exit"] is True
    assert r5["floor_pct"] == 60.0
    assert r5["rule_code"] == "OPT_GAP_TRAIL_TIER3"


def test_profit_guardian_strict_monotonicity_across_steps():
    from app.options.profit_guardian import evaluate_option_profit_ratchet

    entry = 2.00
    prev_floor = 0.0
    floors = []
    highest = entry
    for gain_pct in (10.0, 12.0, 15.0, 20.0, 28.0, 35.0, 45.0, 60.0):
        cur = round(entry * (1.0 + gain_pct / 100.0), 4)
        highest = max(highest, cur)
        res = evaluate_option_profit_ratchet(
            entry_premium=entry,
            current_premium=cur,
            highest_premium_seen=highest,
            peak_pnl_pct=gain_pct,
            prev_floor_premium=prev_floor,
        )
        assert res["should_exit"] is False
        assert res["floor_premium"] > prev_floor
        prev_floor = res["floor_premium"]
        floors.append(prev_floor)

    assert floors == sorted(floors)
    assert len(set(floors)) == len(floors)

    # Pullback intermedio (por encima del piso) NUNCA baja el piso previo
    res_pullback = evaluate_option_profit_ratchet(
        entry_premium=entry,
        current_premium=round(entry * 1.50, 4),
        highest_premium_seen=highest,
        peak_pnl_pct=60.0,
        prev_floor_premium=prev_floor,
    )
    assert res_pullback["floor_premium"] >= prev_floor


def test_peak_profit_ratchet_not_blocked_by_expanding_15m_bb():
    from app.options.exit_engine import evaluate_technical_rules_and_stops

    position = {
        "id": 500,
        "symbol": "AMZN",
        "direction": "long_put",
        "qty": 1,
        "entry_debit": 4.1285,
        "last_mark_price": 4.75,
        "highest_premium_seen": 6.2316,
        "entry_underlying_price": 261.83,
        "entry_total_invested": 412.85,
        "unrealized_pnl": 62.15,
        "unrealized_pnl_pct": 15.05,
        "created_at": "2026-11-16T15:00:00+00:00",
        "exit_plan": {
            "stop_loss_underlying": 266.0,
            "highest_pnl_usd": 210.31,  # Pico de +50.9% ($6.23) -> piso $178.76; cayó >70%!
            "highest_pnl_pct": 50.9,
        },
    }
    tech = {
        "valid": True,
        "symbol": "AMZN",
        "current_price": 260.20,
        "bb_lower_15m": 258.0,
        "bb_upper_15m": 264.0,
        "is_bb_expanding_15m": True,  # Antes bloqueaba tp_peak_profit_ratchet!
        "rvol_15m": 1.60,
        "adx_15m": 30.0,
        "adx_slope_15m": 1.0,
        "plus_di_15m": 12.0,
        "minus_di_15m": 35.0,
        "ema3_15m": 260.0,
        "prev_ema3_15m": 259.9,
    }
    now_dt = datetime.fromisoformat("2026-11-16T15:30:00+00:00")
    should_exit, reason, info = evaluate_technical_rules_and_stops(position, tech, now_dt)
    assert should_exit is True
    assert reason == "tp_peak_profit_ratchet"
    assert info["exit_plan"]["stop_loss_premium"] > 0


def test_micro_pullback_dynamic_trailing_ratchet_locks_gains():
    from app.stocks.micro_pullback_engine import MicroPullbackEngine, ScalpCandidateState

    eng = MicroPullbackEngine()
    eng.enable_runners_15m_1h = True
    cand = ScalpCandidateState("NVDA")
    cand.in_trade = True
    cand.phase = "RUNNER_15M_MODE"
    cand.entry_price = 100.0
    cand.stop_loss = 100.02
    cand.highest_price_reached = 106.0  # +6% pico
    cand.shares = 50
    cand.initial_shares = 100

    bar_pullback = {
        "time": 1700000050,
        "open": 105.0,
        "high": 105.2,
        "low": 104.1,
        "close": 104.2,
        "volume": 10000,
        "is_green": False,
        "lower_wick_ratio": 0.1,
        "upper_wick_ratio": 0.1,
    }
    from unittest.mock import patch
    with patch.object(eng, "_check_rebuys_on_dip"), \
         patch.object(eng, "_is_15m_trend_exhausted", return_value=False):
        eng._manage_active_trade(cand, bar_pullback)

    # 100 + 0.65 * (106 - 100) = 103.90 (en lugar de quedarse en BE 100.02!)
    assert cand.stop_loss == 103.90
    assert cand.in_trade is True


def test_is_option_closing_pending_expires_after_120s():
    from app.options.broker_sync import is_option_closing_pending

    stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=180)).isoformat()
    pos = {
        "id": 1778,
        "symbol": "INTC",
        "expiry": "2026-11-20",
        "strategy_type": "long_put",
        "entry_fills": [{"strike": 57.0, "right": "P"}],
        "exit_plan": {
            "closing_pending": True,
            "closing_requested_at": stale_ts,
        },
    }
    mock_sb = MagicMock()
    assert is_option_closing_pending(mock_sb, pos, max_pending_sec=120.0) is False


def test_dynamic_underlying_trailing_sl_put_descending_and_call_ascending():
    from app.options.profit_guardian import compute_dynamic_underlying_trailing_sl

    # Inicialización automática en PUT sin SL previo
    init_put = compute_dynamic_underlying_trailing_sl(
        entry_underlying=100.0,
        current_underlying=100.0,
        current_sl=0.0,
        is_put=True,
    )
    assert init_put["updated"] is True
    assert init_put["trailing_sl_type"] == "INITIAL_PUT_SL"
    assert init_put["stop_loss_underlying"] == 103.0
    assert init_put["lowest_underlying_seen"] == 100.0

    # Caída progresiva del subyacente en PUT: SL desciende estrictamente en cada tramo
    sl = init_put["stop_loss_underlying"]
    lo = init_put["lowest_underlying_seen"]
    put_sls = []
    for px in (99.0, 98.0, 96.0, 94.0, 90.0):
        res = compute_dynamic_underlying_trailing_sl(
            entry_underlying=100.0,
            current_underlying=px,
            current_sl=sl,
            is_put=True,
            lowest_underlying_seen=lo,
        )
        assert res["updated"] is True
        assert res["stop_loss_underlying"] < sl
        assert res["stop_loss_underlying"] > px
        sl = res["stop_loss_underlying"]
        lo = res["lowest_underlying_seen"]
        put_sls.append(sl)
    assert len(set(put_sls)) == 5
    assert res["trailing_sl_type"] == "BE_LOCK_PLUS_1PCT"
    assert sl < 99.0

    # Rebote tras mínimo: lowest_underlying_seen permanece en 90.0 y techo NO sube
    bounce = compute_dynamic_underlying_trailing_sl(
        entry_underlying=100.0,
        current_underlying=90.80,
        current_sl=sl,
        is_put=True,
        lowest_underlying_seen=lo,
    )
    assert bounce["updated"] is False
    assert bounce["lowest_underlying_seen"] == 90.0
    assert bounce["stop_loss_underlying"] == sl

    # Simetría ascendente en CALL
    init_call = compute_dynamic_underlying_trailing_sl(
        entry_underlying=100.0,
        current_underlying=100.0,
        current_sl=0.0,
        is_put=False,
    )
    assert init_call["stop_loss_underlying"] == 97.0
    sl_c = init_call["stop_loss_underlying"]
    hi_c = init_call["highest_underlying_seen"]
    for px in (101.0, 103.0, 106.0, 110.0):
        rc = compute_dynamic_underlying_trailing_sl(
            entry_underlying=100.0,
            current_underlying=px,
            current_sl=sl_c,
            is_put=False,
            highest_underlying_seen=hi_c,
        )
        assert rc["updated"] is True
        assert rc["stop_loss_underlying"] > sl_c
        assert rc["stop_loss_underlying"] < px
        sl_c = rc["stop_loss_underlying"]
        hi_c = rc["highest_underlying_seen"]

    pullback_c = compute_dynamic_underlying_trailing_sl(
        entry_underlying=100.0,
        current_underlying=109.20,
        current_sl=sl_c,
        is_put=False,
        highest_underlying_seen=hi_c,
    )
    assert pullback_c["updated"] is False
    assert pullback_c["stop_loss_underlying"] == sl_c


def test_exit_engine_put_continuous_descent_and_partial_tp_cushion():
    from app.options.exit_engine import evaluate_technical_rules_and_stops

    # 1. Sin giro bajista de EMA9 15m (ema9 >= prev_ema9), PUT desciende igualmente SL continuo
    pos = {
        "id": 901,
        "symbol": "IWM",
        "strategy_type": "long_put",
        "direction": "bearish",
        "qty": 2,
        "entry_debit": 2.0,
        "last_mark_price": 2.15,
        "unrealized_pnl": 30.0,
        "unrealized_pnl_pct": 7.5,
        "created_at": "2026-11-16T14:00:00+00:00",
        "exit_plan": {
            "entry_underlying_price": 100.0,
            "initial_sl": 103.0,
            "stop_loss_underlying": 103.0,
            "trailing_sl_type": "INITIAL",
        },
    }
    tech = {
        "valid": True,
        "symbol": "IWM",
        "current_price": 98.0,
        "ema3_15m": 98.2,
        "ema9_15m": 99.5,
        "prev_ema9_15m": 99.5,  # Plana -> EMA9_15M no dispara
        "ema3_slope_1h": -0.05,
        "rsi_1h": 42.0,
    }
    now_dt = datetime.fromisoformat("2026-11-16T15:00:00+00:00")
    should_exit, _, info = evaluate_technical_rules_and_stops(pos, tech, now_dt)
    assert should_exit is False
    plan_out = info["exit_plan"]
    assert plan_out["lowest_underlying_seen"] == 98.0
    assert plan_out["stop_loss_underlying"] < 103.0
    assert plan_out["stop_loss_underlying"] > 98.0
    assert plan_out["trailing_sl_type"] == "TRAIL_PUT_CONTINUOUS"

    # 2. TP parcial +20% NO fija stop_loss_underlying por debajo de current_price en PUT
    pos_tp = {
        "id": 902,
        "symbol": "INTC",
        "strategy_type": "long_put",
        "direction": "bearish",
        "qty": 2,
        "entry_debit": 2.0,
        "last_mark_price": 2.50,
        "unrealized_pnl": 100.0,
        "unrealized_pnl_pct": 25.0,
        "created_at": "2026-11-16T14:00:00+00:00",
        "exit_plan": {
            "entry_underlying_price": 56.11,
            "initial_sl": 57.80,
            "stop_loss_underlying": 57.80,
            "partial_tp_taken": False,
        },
    }
    tech_tp = {
        "valid": True,
        "symbol": "INTC",
        "current_price": 56.00,  # 56.11 * 0.99 = 55.55 < 56.00! Antes invertía el techo
        "ema3_15m": 56.10,
        "ema9_15m": 56.50,
        "prev_ema9_15m": 56.50,
        "ema3_slope_1h": -0.04,
        "rsi_1h": 45.0,
    }
    should_exit_tp, reason_tp, info_tp = evaluate_technical_rules_and_stops(pos_tp, tech_tp, now_dt)
    assert should_exit_tp is True
    assert reason_tp == "tp_bb_climax_partial"
    assert info_tp["exit_plan"]["stop_loss_underlying"] > tech_tp["current_price"]


def test_vme_exit_long_put_not_bullish_and_uses_underlying_entry():
    import numpy as np
    import pandas as pd
    from app.stocks.vme_exit_engine import evaluate_vme_exit

    bars = 30
    closes = np.linspace(155.0, 147.0, bars)
    df_15m = pd.DataFrame({
        "open": closes + 0.4,
        "high": closes + 0.8,
        "low": closes - 0.3,
        "close": closes,
        "volume": np.full(bars, 100000.0),
    })
    df_1h = pd.DataFrame({
        "open": closes + 0.6,
        "high": closes + 1.0,
        "low": closes - 0.4,
        "close": closes,
        "volume": np.full(bars, 400000.0),
    })

    # Sin direction explícito, strategy_type="long_put" NO debe tratarse como alcista ni usar entry_debit=3.20 como entry_p
    pos_put = {
        "strategy_type": "long_put",
        "entry_debit": 3.20,
        "entry_underlying_price": 152.0,
        "exit_plan": {
            "entry_underlying_price": 152.0,
            "stop_loss_underlying": 156.0,
        },
    }
    res = evaluate_vme_exit(
        pos_put,
        df_15m=df_15m,
        df_1h=df_1h,
        current_price=147.0,
        current_option_premium=4.10,
        position_age_minutes=20.0,
    )
    assert res["metrics"]["entry_price"] == 152.0
    assert res["new_stop_loss"] < 156.0
    assert res["new_stop_loss"] > 147.0
    assert res["lowest_underlying_seen"] == 147.0


def test_sync_option_exit_plan_initializes_and_descends_put_underlying_sl():
    from app.options.broker_sync import sync_option_exit_plan

    p1 = sync_option_exit_plan(None, entry_debit=3.00, mark_p=3.05, is_put=True, underlying_price=150.0)
    assert p1["entry_underlying_price"] == 150.0
    assert p1["initial_sl"] == 154.5
    assert p1["stop_loss_underlying"] == 154.5
    assert p1["lowest_underlying_seen"] == 150.0
    assert p1["stop_loss_premium"] == 2.1

    p2 = sync_option_exit_plan(p1, entry_debit=3.00, mark_p=4.20, is_put=True, underlying_price=145.0)
    assert p2["lowest_underlying_seen"] == 145.0
    assert p2["stop_loss_underlying"] < p1["stop_loss_underlying"]
    assert p2["stop_loss_underlying"] > 145.0
    assert p2["stop_loss_premium"] > 3.00
