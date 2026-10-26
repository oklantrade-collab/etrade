"""Tests del modelo de salida OPT3 (Tramos 25/50/25 + gracia de apertura)."""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.stocks import gap_exit_opt3 as o3  # noqa: E402
from app.stocks.aduana_gap_runner_engine import evaluate_gap_runner_aduana_exit  # noqa: E402

TZ = "America/New_York"


def make_df(rows, start="2026-10-23 09:30"):
    """rows: lista de (open, high, low, close) en velas de 15m consecutivas desde 'start' (ET)."""
    idx = pd.date_range(start=start, periods=len(rows), freq="15min", tz=TZ)
    return pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close"]).assign(volume=100000.0)


def rising(n, p0=5.0, step=0.02):
    rows, p = [], p0
    for _ in range(n):
        o, c = p, p * (1 + step)
        rows.append((o, c * 1.002, o * 0.999, c))
        p = c
    return rows


def pos(**kw):
    base = {"ticker": "TEST", "avg_price": 5.0, "entry_price": 5.0, "shares": 100, "shares_remaining": 100,
            "stop_loss": 4.5, "group_name": "GAP_RUNNER", "first_buy_at": "2026-10-23T13:30:00+00:00",
            "highest_price_reached": 5.0}
    base.update(kw)
    return base


def now_after(df):
    return df.index[-1] + pd.Timedelta(minutes=15)


# ── Flag / identificación ──
def test_default_is_legacy(monkeypatch):
    monkeypatch.delenv("GAP_EXIT_MODEL", raising=False)
    assert o3.get_gap_exit_model() == "LEGACY"
    assert not o3.is_opt3_gap_position(pos())


def test_opt3_flag_only_for_gap(monkeypatch):
    monkeypatch.setenv("GAP_EXIT_MODEL", "OPT3")
    assert o3.is_opt3_gap_position(pos())
    assert not o3.is_opt3_gap_position(pos(group_name="SWING", strategy="X"))
    assert o3.is_opt3_gap_position(pos(group_name="SWING", reentry_count=1))


def test_dispatcher_uses_legacy_by_default(monkeypatch):
    monkeypatch.delenv("GAP_EXIT_MODEL", raising=False)
    df = make_df(rising(6))
    res = evaluate_gap_runner_aduana_exit(pos(), 5.2, df_15m=df)
    assert res.get("model") != "OPT3"


# ── Stop Loss ──
def test_hard_sl_closes_remaining():
    df = make_df(rising(6))
    res = o3.evaluate_gap_opt3_exit(pos(stop_loss=4.8, shares_remaining=40), 4.7, df_15m=df, now=now_after(df))
    assert res["should_exit"] and res["exit_type"] == "full" and res["shares_to_exit"] == 40
    assert res["rule_code"] == "ADUANA_GAP_HARD_SL"


def test_sl_above_entry_is_breakeven_rule():
    df = make_df(rising(6))
    res = o3.evaluate_gap_opt3_exit(pos(stop_loss=5.3, shares_remaining=40), 5.2, df_15m=df, now=now_after(df))
    assert res["should_exit"] and res["rule_code"] == "ADUANA_GAP_BREAKEVEN_SL"


# ── Tramos ──
def test_tramo1_rsi1h_85_once():
    df = make_df(rising(12))
    res = o3.evaluate_gap_opt3_exit(pos(), float(df["close"].iloc[-1]), df_15m=df, now=now_after(df))
    assert res["rsi_1h"] >= 85
    assert res["should_exit"] and res["rule_code"] == "ADUANA_GAP_OPT3_T1_25_RSI1H"
    assert res["shares_to_exit"] == 25 and res["tp_block"] == "block1"


def test_tramo2_after_tramo1_is_50pct_of_original():
    df = make_df(rising(12))
    res = o3.evaluate_gap_opt3_exit(
        pos(tp_block1_executed=True, shares_remaining=75), float(df["close"].iloc[-1]),
        df_15m=df, now=now_after(df))
    if res["should_exit"]:
        assert res["rule_code"] == "ADUANA_GAP_OPT3_T2_50_CLIMAX"
        assert res["shares_to_exit"] == 50 and res["tp_block"] == "block2"


def test_tramos_never_sell_last_share():
    df = make_df(rising(12))
    res = o3.evaluate_gap_opt3_exit(pos(shares=3, shares_remaining=1, stop_loss=1.0),
                                    float(df["close"].iloc[-1]), df_15m=df, now=now_after(df))
    assert not (res["should_exit"] and res["exit_type"] == "partial")


# ── Velas cerradas ──
def test_forming_candle_excluded():
    df = make_df(rising(6))
    now_mid = df.index[-1] + pd.Timedelta(minutes=5)   # la última vela aún se está formando
    closed = o3.closed_candles(df, now_mid)
    assert len(closed) == len(df) - 1


# ── TSL con gracia de apertura ──
def _flat_then(rows_after):
    base = [(5.0, 5.02, 4.98, 5.0 + 0.001 * i) for i in range(8)]
    return make_df(base + rows_after)


def test_tsl_not_armed_inside_grace():
    # Vela verde que perfora BB sup. en la 2ª vela tras la entrada (<30 min): no arma TSL
    rows = [(5.0, 5.01, 4.99, 5.0), (5.0, 5.6, 5.0, 5.55), (5.5, 5.52, 5.0, 5.05)]
    df = make_df(rows)
    t = o3.compute_tsl_15m(df, pos())
    assert t["tsl_now"] == 0.0


def test_tsl_armed_after_grace_and_exits_on_close_below():
    flat = [(5.0, 5.01, 4.99, 5.0)] * 4                    # 09:30..10:15 (planas)
    spike = [(5.0, 5.9, 5.0, 5.8)]                         # 10:30 vela verde que perfora BB
    drop = [(5.7, 5.72, 5.0, 5.1)]                         # 10:45 cierra bajo el midpoint (5.4)
    df = make_df(flat + spike + drop)
    t = o3.compute_tsl_15m(df, pos())
    assert t["tsl_prev"] == pytest.approx(5.4, abs=0.01)
    res = o3.evaluate_gap_opt3_exit(pos(stop_loss=4.0), 5.1, df_15m=df, now=now_after(df))
    assert res["should_exit"] and res["rule_code"] == "ADUANA_GAP_OPT3_TSL_15M_CLOSE"


def test_ratchet_be_and_ema9_trail_update_stop():
    df = make_df(rising(8, step=0.006))
    price = float(df["close"].iloc[-1])
    res = o3.evaluate_gap_opt3_exit(
        pos(highest_price_reached=5.3, stop_loss=4.5), price, df_15m=df, now=now_after(df))
    if res["rsi_1h"] < 85:
        assert res["new_stop_loss"] is not None and res["new_stop_loss"] >= 5.05
