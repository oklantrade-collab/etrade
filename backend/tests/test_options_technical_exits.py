"""
Test Suite: Reglas Técnicas Institucionales de Cierre y Trailing Stop en Opciones (CALLs y PUTs)
=============================================================================================
Valida:
1. Salida de CALL cuando EMA3 < EMA9 en 15m (y de PUT cuando EMA3 > EMA9).
2. Salida de CALL cuando RSI 1H >= 80 (y de PUT cuando RSI 1H <= 20).
3. Salida de CALL cuando subyacente toca UPPER_6 (y de PUT cuando toca LOWER_6).
4. Salida de CALL cuando pendiente de EMA3 1H se vuelve lateral o descendente (y de PUT lateral o ascendente).
5. Salida de CALL por SIPV SELL (y de PUT por SIPV BUY).
6. SL Dinámico 15m (EMA9 - delta para CALL / EMA9 + delta para PUT).
7. Trailing Stop 1H Midpoint tras perforar Banda de Bollinger con vela verde/roja.
"""

from datetime import datetime, timezone
import pytest
from app.options.exit_engine import evaluate_technical_rules_and_stops


def test_call_exit_ema_cross_15m():
    pos = {"strategy_type": "long_call", "direction": "bullish", "symbol": "SPY"}
    tech = {
        "valid": True,
        "current_price": 770.0,
        "ema3_15m": 768.5,
        "ema9_15m": 769.5,  # EMA3 < EMA9
        "ema3_slope_1h": 0.05,
        "rsi_1h": 60.0
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is True
    assert reason == "ema_cross_15m"


def test_put_exit_ema_cross_15m():
    pos = {"strategy_type": "long_put", "direction": "bearish", "symbol": "SPY"}
    tech = {
        "valid": True,
        "current_price": 760.0,
        "ema3_15m": 762.0,
        "ema9_15m": 761.0,  # EMA3 > EMA9
        "ema3_slope_1h": -0.05,
        "rsi_1h": 40.0
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is True
    assert reason == "ema_cross_15m"


def test_call_exit_rsi_climax_1h():
    pos = {"strategy_type": "long_call", "direction": "bullish", "symbol": "SPY"}
    tech = {
        "valid": True,
        "current_price": 775.0,
        "ema3_15m": 774.0,
        "ema9_15m": 772.0,
        "ema3_slope_1h": 0.10,
        "rsi_1h": 82.5  # RSI >= 80
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is True
    assert reason == "tp_rsi_climax_1h"


def test_put_exit_rsi_climax_1h():
    pos = {"strategy_type": "long_put", "direction": "bearish", "symbol": "SPY"}
    tech = {
        "valid": True,
        "current_price": 750.0,
        "ema3_15m": 751.0,
        "ema9_15m": 753.0,
        "ema3_slope_1h": -0.10,
        "rsi_1h": 17.5  # RSI <= 20
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is True
    assert reason == "tp_rsi_climax_1h"


def test_call_exit_upper_6():
    pos = {"strategy_type": "long_call", "direction": "bullish", "symbol": "SPY"}
    tech = {
        "valid": True,
        "current_price": 782.0,
        "upper_6_1h": 780.0,  # Price >= Upper 6
        "ema3_15m": 781.0,
        "ema9_15m": 779.0,
        "ema3_slope_1h": 0.08,
        "rsi_1h": 68.0
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is True
    assert reason == "tp_upper_6"


def test_put_exit_lower_6():
    pos = {"strategy_type": "long_put", "direction": "bearish", "symbol": "SPY"}
    tech = {
        "valid": True,
        "current_price": 745.0,
        "lower_6_1h": 748.0,  # Price <= Lower 6
        "ema3_15m": 746.0,
        "ema9_15m": 748.0,
        "ema3_slope_1h": -0.08,
        "rsi_1h": 32.0
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is True
    assert reason == "tp_lower_6"


def test_call_exit_ema3_flat_descending():
    pos = {"strategy_type": "long_call", "direction": "bullish", "symbol": "SPY"}
    tech = {
        "valid": True,
        "current_price": 770.0,
        "ema3_15m": 770.5,
        "ema9_15m": 769.5,
        "ema3_slope_1h": -0.02,  # Slope <= 0
        "rsi_1h": 65.0
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is True
    assert reason == "ema3_flat_descending_1h"


def test_put_exit_ema3_flat_ascending():
    pos = {"strategy_type": "long_put", "direction": "bearish", "symbol": "SPY"}
    tech = {
        "valid": True,
        "current_price": 760.0,
        "ema3_15m": 759.5,
        "ema9_15m": 760.5,
        "ema3_slope_1h": 0.03,  # Slope >= 0
        "rsi_1h": 35.0
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is True
    assert reason == "ema3_flat_ascending_1h"


def test_call_exit_sipv_sell():
    pos = {"strategy_type": "long_call", "direction": "bullish", "symbol": "SPY"}
    tech = {
        "valid": True,
        "current_price": 772.0,
        "ema3_15m": 771.5,
        "ema9_15m": 770.0,
        "ema3_slope_1h": 0.05,
        "rsi_1h": 62.0,
        "is_sipv_sell": True
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is True
    assert reason == "sipv_trend_flip_1h"


def test_put_exit_sipv_buy():
    pos = {"strategy_type": "long_put", "direction": "bearish", "symbol": "SPY"}
    tech = {
        "valid": True,
        "current_price": 758.0,
        "ema3_15m": 758.5,
        "ema9_15m": 760.0,
        "ema3_slope_1h": -0.05,
        "rsi_1h": 38.0,
        "is_sipv_buy": True
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is True
    assert reason == "sipv_trend_flip_1h"


def test_trailing_stop_1h_midpoint_call():
    pos = {
        "strategy_type": "long_call",
        "direction": "bullish",
        "symbol": "SPY",
        "exit_plan": {"stop_loss_underlying": 765.0, "trailing_sl_type": "INITIAL"}
    }
    tech = {
        "valid": True,
        "current_price": 772.0,
        "bb_upper_1h": 770.0,
        "candle_closed_high_1h": 773.0,  # High > BB_Upper
        "candle_closed_open_1h": 766.0,
        "candle_closed_close_1h": 772.0,  # Close > Open
        "ema3_15m": 772.0,
        "ema9_15m": 770.5,
        "ema3_slope_1h": 0.08,
        "rsi_1h": 64.0
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is False
    # Midpoint = 766.0 + (772.0 - 766.0) / 2 = 769.0
    new_sl = info["exit_plan"]["stop_loss_underlying"]
    assert new_sl == 769.0
    assert info["exit_plan"]["trailing_sl_type"] == "MIDPOINT_1H"


def test_sl_underlying_pierced():
    pos = {
        "strategy_type": "long_call",
        "direction": "bullish",
        "symbol": "SPY",
        "exit_plan": {"stop_loss_underlying": 768.5, "trailing_sl_type": "EMA9_15M"}
    }
    tech = {
        "valid": True,
        "current_price": 768.20,  # Perforó el SL de 768.50
        "ema3_15m": 769.0,
        "ema9_15m": 768.8,
        "ema3_slope_1h": 0.02,
        "rsi_1h": 58.0
    }
    should_exit, reason, info = evaluate_technical_rules_and_stops(pos, tech, datetime.now(timezone.utc))
    assert should_exit is True
    assert reason == "sl_underlying_pierced"
