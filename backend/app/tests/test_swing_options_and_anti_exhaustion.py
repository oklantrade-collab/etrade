from datetime import datetime, timezone, date, timedelta
import pytest
import pandas as pd
import numpy as np

from app.options.exit_engine import evaluate_technical_rules_and_stops
from app.stocks.stocks_orchestrator import evaluate_5m_breakout, is_overbought


def test_swing_options_block_loss_exit_on_technical_indicators():
    """
    Verifica la regla explícita de negocio:
    Si la opción vence la próxima semana o posteriores (DTE >= 4 días),
    está ESTRICTAMENTE PROHIBIDO cerrarla en pérdida por ruido técnico (EMA3 flat, EMA cross, SL subyacente).
    """
    now_dt = datetime(2026, 10, 26, 15, 0, 0, tzinfo=timezone.utc)
    # Vencimiento la próxima semana (11 días DTE)
    next_week_exp = (now_dt.date() + timedelta(days=11)).isoformat()

    position = {
        "symbol": "DIS",
        "direction": "CALL",
        "strategy_type": "long_call",
        "expiry": next_week_exp,
        "entry_time": (now_dt - timedelta(minutes=45)).isoformat(),
        "unrealized_pnl_pct": -8.5,  # En pérdida
        "exit_plan": {
            "stop_loss_underlying": 112.0,
            "entry_underlying_price": 115.0,
            "trailing_sl_type": "EMA9_15M",
        }
    }

    # Contexto técnico adverso que normalmente activaría ema3_flat_descending_1h o sl_underlying_pierced
    tech = {
        "valid": True,
        "current_price": 111.5,  # Perforó el SL de 112.0
        "ema9_15m": 112.0,
        "prev_ema9_15m": 112.5,
        "ema3_slope_1h": -0.05,  # Slope negativo
        "ema3_15m": 111.0,
        "ema9_15m": 112.0,       # EMA3 < EMA9
        "rsi_1h": 45.0,
    }

    should_exit, reason, info = evaluate_technical_rules_and_stops(position, tech, now_dt)
    # DEBE BLOQUEAR LA SALIDA porque es una opción Swing (DTE 11) en pérdida (-8.5%)
    assert should_exit is False
    assert reason is None


def test_swing_options_allow_exit_when_in_profit():
    """
    Verifica que una opción Swing multi-semana SÍ puede cerrarse
    para tomar o asegurar ganancias si PnL >= +1.0%.
    """
    now_dt = datetime(2026, 10, 26, 15, 0, 0, tzinfo=timezone.utc)
    next_week_exp = (now_dt.date() + timedelta(days=11)).isoformat()

    position = {
        "symbol": "BAC",
        "direction": "CALL",
        "strategy_type": "long_call",
        "expiry": next_week_exp,
        "entry_time": (now_dt - timedelta(minutes=60)).isoformat(),
        "unrealized_pnl_pct": +5.2,  # En ganancia >= +1.0%
        "exit_plan": {
            "stop_loss_underlying": 48.0,
            "entry_underlying_price": 49.0,
            "trailing_sl_type": "EMA9_15M",
        }
    }

    tech = {
        "valid": True,
        "current_price": 50.0,
        "ema9_15m": 49.8,
        "prev_ema9_15m": 49.9,
        "ema3_slope_1h": -0.02,  # Slope 1H plano/descendente
        "ema3_15m": 49.5,
        "ema9_15m": 50.0,
        "rsi_1h": 55.0,
    }

    should_exit, reason, info = evaluate_technical_rules_and_stops(position, tech, now_dt)
    # Se permite salir para asegurar ganancias
    assert should_exit is True
    assert reason == "ema3_flat_descending_1h"


def test_intraday_options_can_exit_on_technical_invalidation():
    """
    Opciones con DTE < 4 (que expiran esta semana o 0DTE)
    sí pueden cerrarse defensivamente por pérdida de momentum.
    """
    now_dt = datetime(2026, 10, 26, 15, 0, 0, tzinfo=timezone.utc)
    # Vence hoy o mañana (DTE = 1)
    short_exp = (now_dt.date() + timedelta(days=1)).isoformat()

    position = {
        "symbol": "SPY",
        "direction": "CALL",
        "strategy_type": "long_call",
        "expiry": short_exp,
        "entry_time": (now_dt - timedelta(minutes=30)).isoformat(),
        "unrealized_pnl_pct": -5.0,
        "exit_plan": {
            "stop_loss_underlying": 580.0,
            "trailing_sl_type": "EMA9_15M",
        }
    }

    tech = {
        "valid": True,
        "current_price": 579.5,  # Perforó SL
        "ema9_15m": 580.0,
        "prev_ema9_15m": 580.5,
        "ema3_slope_1h": -0.01,
        "rsi_1h": 40.0,
    }

    should_exit, reason, info = evaluate_technical_rules_and_stops(position, tech, now_dt)
    assert should_exit is True
    assert reason == "sl_underlying_pierced"


def test_stocks_anti_exhaustion_rsi_cap():
    """
    Verifica que is_overbought bloquee acciones con RSI excesivo:
    - Normales: RSI >= 72
    - Alpha Runners: RSI >= 78 (nunca 92)
    """
    cfg = {"apex_max_overbought_rsi": 72}

    # Acción normal con RSI 74
    snap_normal = {"rsi_14": 74.0, "price": 50.0, "is_intraday_alpha": False}
    res_norm = is_overbought(snap_normal, cfg)
    assert res_norm["blocked"] is True

    # Alpha runner con RSI 82 (en el código viejo pasaba hasta 92, ahora debe bloquearse)
    snap_alpha = {"rsi_14": 82.0, "price": 50.0, "is_intraday_alpha": True}
    res_alpha = is_overbought(snap_alpha, cfg)
    assert res_alpha["blocked"] is True
    assert "RSI Agotamiento Alpha Runner" in res_alpha["reason"]


def test_stocks_evaluate_5m_breakout_rejects_extended_rubber_band():
    """
    Verifica que evaluate_5m_breakout rechace precios sobreextendidos de EMA20 > 2.0%
    y RSI 5m > 70.0 aunque el EMA stack sea alcista.
    """
    dates = pd.date_range("2026-10-26 09:30", periods=50, freq="5min")
    # Simular una subida vertical (agotamiento parabólico)
    prices = [10.0 + (i * 0.25) for i in range(50)]
    df_5m = pd.DataFrame({"close": prices, "high": [p + 0.1 for p in prices], "low": [p - 0.1 for p in prices]}, index=dates)

    # DataFrame 1D mock
    dates_1d = pd.date_range("2025-01-01", periods=250, freq="D")
    prices_1d = [10.0 + (i * 0.1) for i in range(250)]
    df_1d = pd.DataFrame({"close": prices_1d}, index=dates_1d)

    snap = {"price": prices[-1]}
    res = evaluate_5m_breakout("TEST", df_5m, df_1d, snap)

    # Debe rechazar por agotamiento (RSI > 70 o sobreextensión de EMA20)
    assert res["triggered"] is False
    assert "sobrecomprado" in res["reason"] or "sobreextendido" in res["reason"]
