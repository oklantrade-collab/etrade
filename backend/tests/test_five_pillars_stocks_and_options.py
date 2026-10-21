import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from app.stocks.aduana_gap_runner_engine import (
    evaluate_gap_runner_entry_tranches,
    evaluate_gap_runner_aduana_exit
)
from app.options.aduana_gap_runner_options import evaluate_options_gap_aduana_exit
from app.stocks.vme_exit_engine import evaluate_vme_exit


def create_sample_5m_df(prices, vwap_val=100.0, volume=50000, start_hour_utc=14):
    """Helper to create realistic 5m DataFrame."""
    dates = pd.date_range(f"2026-10-20 {start_hour_utc:02d}:00:00", periods=len(prices), freq="5min", tz="UTC")
    data = []
    for i, p in enumerate(prices):
        prev = prices[i-1] if i > 0 else p
        data.append({
            "open": prev,
            "high": max(prev, p) * 1.002,
            "low": min(prev, p) * 0.998,
            "close": p,
            "volume": volume
        })
    df = pd.DataFrame(data, index=dates)
    return df


def test_pilar1_morning_window_blocks_late_gap_entries():
    """Pilar 1: Compras en Gaps después de las 11:15 ET (15:15 UTC) son bloqueadas."""
    # Hora: 18:00 UTC (14:00 ET / 2:00 PM) -> Tarde
    df_5m = create_sample_5m_df([100.0, 101.0, 102.0], start_hour_utc=18)
    
    res = evaluate_gap_runner_entry_tranches(
        ticker="TEST",
        df_5m=df_5m,
        df_15m=None,
        df_1h=None,
        gap_pct=3.5,
        config={"skip_time_window_check": False}
    )
    assert res["should_enter"] is False
    assert "Fuera de ventana de apertura institucional" in res["reason"]


def test_pilar2_buys_blocked_if_price_below_vwap():
    """Pilar 2: Compras LONG son bloqueadas si el precio cotiza por debajo del VWAP."""
    # Precios arrancan en 105, bajan a 98. El VWAP acumulado queda sobre 100
    # Último precio: 98.0 (< VWAP)
    df_5m = create_sample_5m_df([105.0, 104.0, 102.0, 98.0], start_hour_utc=14)
    
    res = evaluate_gap_runner_entry_tranches(
        ticker="TEST",
        df_5m=df_5m,
        df_15m=None,
        df_1h=None,
        gap_pct=2.5,
        config={"skip_time_window_check": True} # aislar prueba a VWAP
    )
    assert res["should_enter"] is False
    assert "Filtro Maestro VWAP" in res["reason"]


def test_pilar3_breakeven_lock_stocks_at_1pct_gain():
    """Pilar 3: En STOCKS, al superar +1.0% de ganancia, el SL se asegura en entrada + $0.02."""
    pos = {
        "ticker": "TALO",
        "avg_price": 10.00,
        "shares": 200,
        "stop_loss": 9.50,
        "strategy_group": "GAP_RUNNER"
    }
    # Precio sube a 10.15 (+1.5% de ganancia)
    res = evaluate_gap_runner_aduana_exit(
        position=pos,
        current_price=10.15,
        df_5m=None,
        df_15m=None,
        df_1h=None
    )
    assert res["new_stop_loss"] == 10.02
    assert "ADUANA_GAP_BREAKEVEN_LOCK_1PCT" in res["rule_code"]
    assert res["should_exit"] is False # solo sube stop, no cierra


def test_pilar3_breakeven_shield_options_call():
    """Pilar 3 (Opciones): CALL con ganancia pico en prima >= +15% o subyacente >= +1% protege costo."""
    pos = {
        "id": "opt-call-be",
        "symbol": "SPY",
        "direction": "CALL",
        "entry_debit": 5.00,
        "entry_underlying_price": 765.0,
        "highest_premium_seen": 5.85, # +17% pico en prima
        "qty": 2
    }
    # Prima retrocede a 5.03 (en costo de entrada * 1.01)
    res = evaluate_options_gap_aduana_exit(
        position=pos,
        current_underlying_price=773.0, # +1.04% en subyacente
        current_option_premium=5.03
    )
    assert res["should_exit"] is True
    assert res["rule_code"] == "OPT_GAP_CALL_BREAKEVEN"
    assert "Breakeven Shield CALL" in res["reason"]


def test_pilar4_vwap_support_invalidation_exit_stocks():
    """Pilar 4: Si una acción en LONG pierde el VWAP por más de -0.4%, se cierra de inmediato."""
    # Creamos velas donde VWAP es ~100 y el último precio perfora a 99.0 (-1.0% bajo VWAP)
    df_5m = create_sample_5m_df([100.0, 100.5, 99.9, 99.0], start_hour_utc=14)
    pos = {
        "ticker": "CRWV",
        "avg_price": 100.0,
        "shares": 100,
        "stop_loss": 95.0
    }
    res = evaluate_gap_runner_aduana_exit(
        position=pos,
        current_price=99.0,
        df_5m=df_5m
    )
    assert res["should_exit"] is True
    assert res["rule_code"] == "ADUANA_GAP_VWAP_INVALIDATION"
    assert "perforó soporte de VWAP" in res["reason"]


def test_pilar4_vwap_support_invalidation_exit_options_call():
    """Pilar 4 (Opciones): Si el subyacente de un CALL perfora su VWAP por más del -0.4%, salida defensiva."""
    df_5m = create_sample_5m_df([100.0, 100.5, 99.9, 99.2], start_hour_utc=14)
    pos = {
        "symbol": "AAPL",
        "direction": "CALL",
        "entry_debit": 4.00,
        "entry_underlying_price": 100.0
    }
    # Prima actual cae -8% y subyacente perforó VWAP
    res = evaluate_options_gap_aduana_exit(
        position=pos,
        current_underlying_price=99.2,
        current_option_premium=3.65,
        df_5m=df_5m
    )
    assert res["should_exit"] is True
    assert res["rule_code"] == "OPT_GAP_CALL_EXIT_VWAP"
    assert "perforó su VWAP" in res["reason"]
