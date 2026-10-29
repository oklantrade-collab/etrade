"""
test_golden_hour_eod_and_climax_exit.py
=======================================
Suite de pruebas unitarias para el Protocolo EOD Golden Hour (15:00-15:55 ET)
y las salidas por Clímax Fibonacci (UPPER_5/UPPER_6) y RSI >= 80.
"""

import pytest
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.stocks.gap_exit_opt3 import evaluate_gap_opt3_exit
from app.stocks.aduana_stocks_exit_engine import evaluate_aduana_stocks_exit

ET_TZ = ZoneInfo("America/New_York")


def _make_df_15m(prices, end_time_et="2026-10-28 15:00:00"):
    n = len(prices)
    end_dt = datetime.strptime(end_time_et, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET_TZ)
    idx = [end_dt - pd.Timedelta(minutes=15 * (n - 1 - i)) for i in range(n)]
    df = pd.DataFrame({
        "open": [p * 0.99 for p in prices],
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.98 for p in prices],
        "close": prices,
        "volume": [100000.0] * n,
    }, index=pd.DatetimeIndex(idx))
    return df


def _make_df_5m(prices, end_time_et="2026-10-28 15:35:00"):
    n = len(prices)
    end_dt = datetime.strptime(end_time_et, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET_TZ)
    idx = [end_dt - pd.Timedelta(minutes=5 * (n - 1 - i)) for i in range(n)]
    df = pd.DataFrame({
        "open": [p * 0.99 for p in prices],
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.98 for p in prices],
        "close": prices,
        "volume": [50000.0] * n,
    }, index=pd.DatetimeIndex(idx))
    return df


def _make_df_1d(prices):
    n = len(prices)
    idx = pd.date_range(end="2026-10-28", periods=n, freq="D", tz=ET_TZ)
    df = pd.DataFrame({
        "open": [p * 0.98 for p in prices],
        "high": [p * 1.02 for p in prices],
        "low": [p * 0.97 for p in prices],
        "close": prices,
        "volume": [1000000.0] * n,
    }, index=idx)
    return df


# ─────────────────────────────────────────────────────────────
# 1. PRUEBAS DE GOLDEN HOUR EOD EN GAP_EXIT_OPT3
# ─────────────────────────────────────────────────────────────

def test_opt3_golden_hour_fase1_tp50():
    """En la ventana 15:00-15:30 ET con ganancia >= +5%, debe ejecutar TP Parcial del 50%."""
    pos = {
        "ticker": "AIOK", "entry_price": 20.0, "avg_price": 20.0,
        "shares": 20, "shares_remaining": 20, "stop_loss": 19.0,
        "first_buy_at": "2026-10-28T14:55:00-04:00",
        "tp_block1_executed": False, "golden_hour_tp_executed": False
    }
    cur_p = 26.0  # +30% de ganancia
    now_gh = pd.Timestamp("2026-10-28 15:15:00", tz="America/New_York")
    d15 = _make_df_15m([19.0, 19.5, 20.0, 21.0, 22.0, 24.0, 26.0], end_time_et="2026-10-28 15:00:00")
    d5 = _make_df_5m([24.0, 25.0, 25.5, 26.0], end_time_et="2026-10-28 15:15:00")

    res = evaluate_gap_opt3_exit(pos, cur_p, df_5m=d5, df_15m=d15, now=now_gh)
    assert res["should_exit"] is True
    assert res["exit_type"] == "partial"
    assert res["rule_code"] == "ADUANA_GOLDEN_HOUR_TP50"
    assert res["pct"] == 50
    assert res["shares_to_exit"] == 10


def test_opt3_golden_hour_fase2_weakness():
    """En la ventana 15:30-15:50 ET, si EMA3 de 5m muestra debilidad, debe liquidar el remanente."""
    pos = {
        "ticker": "AIOK", "entry_price": 20.0, "avg_price": 20.0,
        "shares": 20, "shares_remaining": 10, "stop_loss": 22.0,
        "first_buy_at": "2026-10-28T14:55:00-04:00",
        "tp_block1_executed": True, "golden_hour_tp_executed": True
    }
    cur_p = 27.0  # +35% de ganancia pero 5m cae
    now_gh = pd.Timestamp("2026-10-28 15:35:00", tz="America/New_York")
    d15 = _make_df_15m([20.0, 22.0, 24.0, 27.0, 28.0, 27.5], end_time_et="2026-10-28 15:30:00")
    # 5m descendente: 29.5 -> 28.5 -> 27.5 -> 27.0
    d5 = _make_df_5m([29.5, 28.5, 27.5, 27.0], end_time_et="2026-10-28 15:35:00")

    res = evaluate_gap_opt3_exit(pos, cur_p, df_5m=d5, df_15m=d15, now=now_gh)
    assert res["should_exit"] is True
    assert res["exit_type"] == "full"
    assert res["rule_code"] == "ADUANA_GOLDEN_HOUR_EXIT_WEAKNESS"
    assert res["shares_to_exit"] == 10
    assert res["pct"] == 100


def test_opt3_golden_hour_fase3_hard100():
    """A partir de las 15:50 ET con ganancia >= +5%, liquidación incondicional del 100%."""
    pos = {
        "ticker": "AIOK", "entry_price": 20.0, "avg_price": 20.0,
        "shares": 20, "shares_remaining": 10, "stop_loss": 23.0,
        "first_buy_at": "2026-10-28T14:55:00-04:00",
    }
    cur_p = 28.0
    now_gh = pd.Timestamp("2026-10-28 15:52:00", tz="America/New_York")
    d15 = _make_df_15m([20.0, 22.0, 25.0, 28.0], end_time_et="2026-10-28 15:45:00")

    res = evaluate_gap_opt3_exit(pos, cur_p, df_15m=d15, now=now_gh)
    assert res["should_exit"] is True
    assert res["exit_type"] == "full"
    assert res["rule_code"] == "ADUANA_GOLDEN_HOUR_EOD_HARD100"
    assert res["shares_to_exit"] == 10


# ─────────────────────────────────────────────────────────────
# 2. PRUEBAS DE CLÍMAX FIBONACCI / RSI EN GAP_EXIT_OPT3
# ─────────────────────────────────────────────────────────────

def test_opt3_climax_rsi15m_extreme():
    """Si RSI 15m >= 80 en horario normal (11:00 ET), dispara toma de ganancia clímax."""
    pos = {
        "ticker": "AIOK", "entry_price": 20.0, "avg_price": 20.0,
        "shares": 20, "shares_remaining": 20, "stop_loss": 19.0,
        "first_buy_at": "2026-10-28T09:30:00-04:00",
        "tp_block1_executed": False, "tp_block2_executed": False
    }
    # Serie de velas 15m con subida parabólica para forzar RSI 15m > 80
    prices = [20.0, 20.2, 20.5, 21.0, 22.0, 23.5, 25.0, 27.0, 29.5]
    d15 = _make_df_15m(prices, end_time_et="2026-10-28 11:00:00")
    cur_p = 29.5
    now_dt = pd.Timestamp("2026-10-28 11:05:00", tz="America/New_York")

    res = evaluate_gap_opt3_exit(pos, cur_p, df_15m=d15, now=now_dt)
    assert res["rsi_15m"] >= 80.0
    assert res["should_exit"] is True
    assert res["rule_code"] in ("ADUANA_GAP_OPT3_T1_CLIMAX", "ADUANA_GAP_OPT3_T1_25_RSI1H")
    assert res["exit_type"] == "partial"
    assert res["pct"] in (25, 50)


def test_opt3_ratchet_peak_40_lock():
    """Si el pico alcanzó +40% de ganancia, el Stop Loss debe asegurarse al 80% del pico."""
    pos = {
        "ticker": "AIOK", "entry_price": 20.0, "avg_price": 20.0,
        "shares": 20, "shares_remaining": 10, "stop_loss": 19.0,
        "highest_price_reached": 29.74,  # +48.7% peak
        "first_buy_at": "2026-10-28T09:30:00-04:00",
        "tp_block1_executed": True, "tp_block2_executed": True
    }
    cur_p = 28.0
    now_dt = pd.Timestamp("2026-10-28 12:00:00", tz="America/New_York")
    d15 = _make_df_15m([20.0, 21.0, 23.0, 25.0, 27.0, 28.0], end_time_et="2026-10-28 11:45:00")

    res = evaluate_gap_opt3_exit(pos, cur_p, df_15m=d15, now=now_dt)
    # 80% de 29.74 = 23.79
    expected_sl = round(29.74 * 0.80, 2)
    assert res["new_stop_loss"] is not None
    assert res["new_stop_loss"] >= expected_sl


# ─────────────────────────────────────────────────────────────
# 3. PRUEBAS DE GOLDEN HOUR EN ADUANA_STOCKS_EXIT_ENGINE
# ─────────────────────────────────────────────────────────────

def test_aduana_engine_golden_hour_fase1():
    """evaluate_aduana_stocks_exit debe ejecutar TP 50% en Golden Hour Fase 1 (15:10 ET)."""
    pos = {
        "ticker": "AIOK", "avg_price": 20.0, "shares": 20, "shares_remaining": 20,
        "first_buy_at": "2026-10-28T14:55:00Z", "side": "long",
        "tp_block1_executed": False, "golden_hour_tp_executed": False
    }
    cur_p = 25.0  # +25%
    ref_time = datetime(2026, 10, 28, 15, 10, tzinfo=ET_TZ)
    d15 = _make_df_15m([20.0, 21.0, 23.0, 25.0], end_time_et="2026-10-28 15:00:00")
    d5 = _make_df_5m([23.0, 24.0, 25.0], end_time_et="2026-10-28 15:10:00")

    res = evaluate_aduana_stocks_exit(pos, cur_p, df_5m=d5, df_15m=d15, now_dt=ref_time)
    assert res["should_close"] is True
    assert res["action"] == "CLOSE_PARTIAL_50"
    assert res["pct_to_close"] == 50
    assert res["rule_code"] == "ADUANA_STK_GOLDEN_HOUR_TP50"
    assert res["shares_to_close"] == 10


def test_aduana_engine_golden_hour_fase2_weakness():
    """evaluate_aduana_stocks_exit debe liquidar remanente en Fase 2 (15:40 ET) si 5m flaquea."""
    pos = {
        "ticker": "AIOK", "avg_price": 20.0, "shares": 20, "shares_remaining": 10,
        "first_buy_at": "2026-10-28T14:55:00Z", "side": "long",
        "tp_block1_executed": True, "golden_hour_tp_executed": True
    }
    cur_p = 26.0  # +30% pero decayendo en 5m
    ref_time = datetime(2026, 10, 28, 15, 40, tzinfo=ET_TZ)
    d15 = _make_df_15m([20.0, 23.0, 27.0, 26.0], end_time_et="2026-10-28 15:30:00")
    d5 = _make_df_5m([28.0, 27.0, 26.0], end_time_et="2026-10-28 15:40:00")

    res = evaluate_aduana_stocks_exit(pos, cur_p, df_5m=d5, df_15m=d15, now_dt=ref_time)
    assert res["should_close"] is True
    assert res["action"] == "CLOSE_TOTAL"
    assert res["pct_to_close"] == 100
    assert res["rule_code"] == "ADUANA_STK_GOLDEN_HOUR_WEAKNESS"
    assert res["shares_to_close"] == 10
