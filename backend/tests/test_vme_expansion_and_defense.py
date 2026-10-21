"""
Test Suite: VOLATILITY MOMENTUM EXPANSION (VME) Engine & Exit Defense
Pruebas exhaustivas para la nueva estrategia VME en STOCKS y OPCIONES:
1. Evaluación de Entrada VME Bullish (LONGs / CALLs).
2. Evaluación de Entrada VME Bearish (PUTs).
3. Veto ante RSI 1H sobreextendido (> 65 o < 35) o fallo de medias macro (EMA20 vs EMA50).
4. 5 Gatillos de Salida en Cascada:
   - Ribbon Break 15m (EMA3 < EMA9)
   - RSI Climax 1H (>= 80 o <= 20)
   - Bandas Fibonacci Extremas (UPPER_5 / UPPER_6)
   - Inflexión de Pendiente EMA3 1H (<= 0)
   - SIPV Reversión 1H
5. Stop Loss Dinámico 15m (EMA9 Ratchet con Delta Adaptativo y Monotonicidad).
6. Trailing Stop Híbrido 15m (50% Cuerpo + Filtro ATR + Piso VWAP).
7. Defensas de Prima de Opciones (Hard SL -35%, Breakeven Shield +15%, Ratchet Tier 2 +30%, Stall Guard).
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

from app.stocks.vme_expansion_engine import evaluate_vme_expansion
from app.stocks.vme_exit_engine import evaluate_vme_exit


def _create_mock_dataframes(
    trend="up",
    n_15m=30,
    n_1h=30,
    rsi_1h=55.0,
    adx_15m=32.0,
    price=100.0,
    vwap=99.0
):
    """Genera dataframes sintéticos de 15m y 1H con indicadores configurables."""
    dates_15m = pd.date_range(end=datetime.now(timezone.utc), periods=n_15m, freq="15min")
    dates_1h = pd.date_range(end=datetime.now(timezone.utc), periods=n_1h, freq="1h")

    # 15m DataFrame
    df_15m = pd.DataFrame(index=dates_15m)
    if trend == "up":
        df_15m["close"] = np.linspace(price - 5, price, n_15m)
        df_15m["open"] = df_15m["close"] - 0.4
        df_15m["high"] = df_15m["close"] + 0.3
        df_15m["low"] = df_15m["open"] - 0.2
        df_15m["volume"] = np.linspace(10000, 25000, n_15m)
        df_15m["ema_3"] = df_15m["close"] + 0.1
        df_15m["ema_9"] = df_15m["close"] - 0.3
        df_15m["ema_20"] = df_15m["close"] - 0.8
        df_15m["di_plus"] = 30.0
        df_15m["di_minus"] = 14.0
    else:
        df_15m["close"] = np.linspace(price + 5, price, n_15m)
        df_15m["open"] = df_15m["close"] + 0.4
        df_15m["high"] = df_15m["open"] + 0.2
        df_15m["low"] = df_15m["close"] - 0.3
        df_15m["volume"] = np.linspace(10000, 25000, n_15m)
        df_15m["ema_3"] = df_15m["close"] - 0.1
        df_15m["ema_9"] = df_15m["close"] + 0.3
        df_15m["ema_20"] = df_15m["close"] + 0.8
        df_15m["di_plus"] = 14.0
        df_15m["di_minus"] = 30.0

    df_15m["adx_14"] = adx_15m
    df_15m["atr_14"] = 1.50
    df_15m["vwap"] = vwap
    df_15m["rvol"] = 2.2
    df_15m["bb_upper"] = df_15m["close"] + 1.2
    df_15m["bb_lower"] = df_15m["close"] - 1.2

    # 1H DataFrame
    df_1h = pd.DataFrame(index=dates_1h)
    if trend == "up":
        df_1h["close"] = np.linspace(price - 10, price, n_1h)
        df_1h["open"] = df_1h["close"] - 0.5
        df_1h["high"] = df_1h["close"] + 0.4
        df_1h["low"] = df_1h["open"] - 0.3
        df_1h["ema_3"] = df_1h["close"] + 0.2
        df_1h["ema_9"] = df_1h["close"] - 0.4
        df_1h["ema_20"] = df_1h["close"] - 1.0
        df_1h["ema_50"] = df_1h["close"] - 2.5
    else:
        df_1h["close"] = np.linspace(price + 10, price, n_1h)
        df_1h["open"] = df_1h["close"] + 0.5
        df_1h["high"] = df_1h["open"] + 0.3
        df_1h["low"] = df_1h["close"] - 0.4
        df_1h["ema_3"] = df_1h["close"] - 0.2
        df_1h["ema_9"] = df_1h["close"] + 0.4
        df_1h["ema_20"] = df_1h["close"] + 1.0
        df_1h["ema_50"] = df_1h["close"] + 2.5

    df_1h["rsi_14"] = rsi_1h

    return df_15m, df_1h


# ════════════════════════════════════════════════════════════
# 1. PRUEBAS DE ENTRADA VME (STOCKS Y OPCIONES)
# ════════════════════════════════════════════════════════════

def test_vme_expansion_bullish_entry_approved():
    """Verifica que un setup alcista óptimo sea aprobado con rank competitivo (99.6 - 99.8)."""
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=100.0, vwap=98.5, rsi_1h=58.0, adx_15m=30.0)

    res = evaluate_vme_expansion("NVDA", df_15m, df_1h, current_price=100.0, direction="bullish")

    assert res["should_enter"] is True
    assert res["direction"] == "bullish"
    assert res["rule_code"] == "VME_EXPANSION_STK"
    assert res["group_name"] == "VOLATILITY_EXPANSION"
    assert res["composite_rank"] >= 99.6
    assert res["initial_sl"] < 100.0
    assert "VME Bullish Power Trend" in res["reason"]


def test_vme_expansion_rank_boost_for_explosive_adx():
    """Verifica que cuando ADX >= 35 y RVOL >= 2.5 el rank alcance 99.9 para liderar."""
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=100.0, vwap=98.0, adx_15m=38.0)
    df_15m["rvol"] = 2.8

    res = evaluate_vme_expansion("TSLA", df_15m, df_1h, current_price=100.0, direction="bullish")

    assert res["should_enter"] is True
    assert res["composite_rank"] == 99.9  # Supera a Open Gap Runner 99.8


def test_vme_expansion_bullish_blocks_on_overbought_rsi_1h():
    """Verifica que si RSI en 1H > 65.0 la entrada sea bloqueada por falta de pista libre."""
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=100.0, rsi_1h=72.0)

    res = evaluate_vme_expansion("AAPL", df_15m, df_1h, current_price=100.0, direction="bullish")

    assert res["should_enter"] is False
    assert "RSI1H" in res["reason"]


def test_vme_expansion_bullish_blocks_when_price_below_vwap():
    """Verifica bloqueo si el precio cotiza por debajo del VWAP en 15m."""
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=98.0, vwap=100.0)

    res = evaluate_vme_expansion("MSFT", df_15m, df_1h, current_price=98.0, direction="bullish")

    assert res["should_enter"] is False
    assert "VWAP" in res["reason"]


def test_vme_expansion_bearish_put_entry_approved():
    """Verifica que una tendencia bajista con volumen y medias en cascada apruebe entrada para PUTs."""
    df_15m, df_1h = _create_mock_dataframes(trend="down", price=100.0, vwap=101.5, rsi_1h=42.0, adx_15m=28.0)

    res = evaluate_vme_expansion("AMD", df_15m, df_1h, current_price=100.0, direction="bearish")

    assert res["should_enter"] is True
    assert res["direction"] == "bearish"
    assert res["rule_code"] == "VME_EXPANSION_PUT"
    assert res["initial_sl"] > 100.0
    assert "VME Bearish Breakdown Trend" in res["reason"]


def test_vme_expansion_bearish_blocks_on_oversold_rsi_1h():
    """Verifica que si RSI en 1H < 35.0 en bajista se bloquee la compra de PUTs por sobreventa."""
    df_15m, df_1h = _create_mock_dataframes(trend="down", price=100.0, rsi_1h=28.0)

    res = evaluate_vme_expansion("AMD", df_15m, df_1h, current_price=100.0, direction="bearish")

    assert res["should_enter"] is False


# ════════════════════════════════════════════════════════════
# 2. PRUEBAS DE SALIDA Y LOS 5 GATILLOS DE CIERRE EN CASCADA
# ════════════════════════════════════════════════════════════

def test_vme_exit_trigger_1_ribbon_break_15m():
    """Gatillo 1: Quiebre de Ribbon 15m (EMA3 < EMA9) cierra inmediatamente la posición."""
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=105.0)
    # Simular quiebre de Ribbon en la última vela (EMA3 cae bajo EMA9)
    df_15m.loc[df_15m.index[-1], "ema_3"] = 104.2
    df_15m.loc[df_15m.index[-1], "ema_9"] = 104.8

    pos = {"direction": "long", "entry_price": 100.0, "stop_loss": 98.0}
    res = evaluate_vme_exit(pos, df_15m, df_1h, current_price=105.0)

    assert res["should_exit"] is True
    assert res["exit_type"] == "FULL"
    assert res["rule_code"] == "VME_EXIT_RIBBON_15M"


def test_vme_exit_trigger_2_rsi_climax_1h():
    """Gatillo 2: Clímax de euforia (RSI 1H >= 80) ejecuta toma de ganancias total."""
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=112.0, rsi_1h=82.5)

    pos = {"direction": "long", "entry_price": 100.0, "stop_loss": 98.0}
    res = evaluate_vme_exit(pos, df_15m, df_1h, current_price=112.0)

    assert res["should_exit"] is True
    assert res["exit_type"] == "FULL"
    assert res["rule_code"] == "VME_EXIT_RSI_CLIMAX_1H"


def test_vme_exit_trigger_3_fibonacci_upper5_partial_and_upper6_full():
    """Gatillo 3: Alcance de UPPER_5 cierra 50% (TP1), y UPPER_6 cierra 100%."""
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=108.0)
    df_15m.loc[df_15m.index[-1], "upper_5"] = 107.5
    df_15m.loc[df_15m.index[-1], "upper_6"] = 111.0

    pos = {"direction": "long", "entry_price": 100.0, "stop_loss": 98.0}

    # Caso A: Precio en 108.0 (supera UPPER_5 = 107.5 pero menor a UPPER_6 = 111.0)
    res_tp1 = evaluate_vme_exit(pos, df_15m, df_1h, current_price=108.0)
    assert res_tp1["should_exit"] is True
    assert res_tp1["exit_type"] == "PARTIAL"
    assert res_tp1["partial_ratio"] == 0.50
    assert res_tp1["rule_code"] == "VME_EXIT_UPPER5_TP1"

    # Caso B: Precio en 111.5 (supera UPPER_6) -> Cierre Total
    res_tp2 = evaluate_vme_exit(pos, df_15m, df_1h, current_price=111.5)
    assert res_tp2["should_exit"] is True
    assert res_tp2["exit_type"] == "FULL"
    assert res_tp2["rule_code"] == "VME_EXIT_UPPER6_TOTAL"


def test_vme_exit_trigger_4_ema3_slope_1h_inflection():
    """Gatillo 4: Inflexión de EMA3 en 1H a plano o negativo en ganancia asegura PnL."""
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=105.0)
    # EMA3 actual igual o menor al previo (pendiente <= 0)
    df_1h.loc[df_1h.index[-1], "ema_3"] = 103.5
    df_1h.loc[df_1h.index[-2], "ema_3"] = 103.8

    pos = {"direction": "long", "entry_price": 100.0, "stop_loss": 98.0}
    res = evaluate_vme_exit(pos, df_15m, df_1h, current_price=105.0)

    assert res["should_exit"] is True
    assert res["rule_code"] == "VME_EXIT_EMA3_SLOPE_1H"


def test_vme_exit_trigger_5_sipv_reversal_signal():
    """Gatillo 5: Patrón de reversión de velas SIPV 1H (SELL) cierra de inmediato."""
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=104.0)

    pos = {"direction": "long", "entry_price": 100.0, "stop_loss": 98.0}
    res = evaluate_vme_exit(pos, df_15m, df_1h, current_price=104.0, sipv_signal_1h="BEARISH_ENGULFING_SELL")

    assert res["should_exit"] is True
    assert res["rule_code"] == "VME_EXIT_SIPV_1H"


# ════════════════════════════════════════════════════════════
# 3. PRUEBAS DE STOP LOSS DINÁMICO Y TRAILING STOP HÍBRIDO 15M
# ════════════════════════════════════════════════════════════

def test_vme_dynamic_stop_loss_15m_ema9_ratchet_and_monotonic():
    """Verifica que el SL dinámico suba con EMA9 - delta y nunca retroceda."""
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=102.0)
    # EMA9 actual = 100.5, EMA9 previo = 99.5 (subiendo)
    df_15m.loc[df_15m.index[-1], "ema_9"] = 100.5
    df_15m.loc[df_15m.index[-2], "ema_9"] = 99.5
    df_15m.loc[df_15m.index[-1], "atr_14"] = 1.0  # delta = 0.35 * 1.0 = 0.35

    pos = {"direction": "long", "entry_price": 100.0, "stop_loss": 97.0}
    res = evaluate_vme_exit(pos, df_15m, df_1h, current_price=102.0)

    # prop_sl = 100.5 - 0.35 = 100.15
    assert res["new_stop_loss"] == 100.15
    assert res["new_stop_loss"] > pos["stop_loss"]

    # Monotonicidad: si EMA9 bajara en vela correctiva, el SL debe mantenerse en 100.15
    df_15m.loc[df_15m.index[-1], "ema_9"] = 99.0
    pos_high_sl = {"direction": "long", "entry_price": 100.0, "stop_loss": 100.15}
    res2 = evaluate_vme_exit(pos_high_sl, df_15m, df_1h, current_price=102.0)
    assert res2["new_stop_loss"] == 100.15


def test_vme_hybrid_trailing_stop_15m_50pct_body_with_vwap_floor():
    """
    Verifica que al romper Bollinger Upper en 15m con vela verde:
    - Se ancle en el 50% del cuerpo si es potente.
    - Se asegure que no esté por debajo del VWAP si está en ganancia.
    """
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=106.0, vwap=102.0)
    # Simular vela verde impulsiva que rompe banda superior (High > BB_Upper)
    df_15m.loc[df_15m.index[-1], "open"] = 103.0
    df_15m.loc[df_15m.index[-1], "close"] = 106.0
    df_15m.loc[df_15m.index[-1], "high"] = 106.5
    df_15m.loc[df_15m.index[-1], "low"] = 102.8
    df_15m.loc[df_15m.index[-1], "bb_upper"] = 105.0
    df_15m.loc[df_15m.index[-1], "atr_14"] = 1.20  # body = 3.0 >= 0.5 * 1.2 = 0.60

    # mid_body = 103.0 + 3.0 / 2 = 104.50
    pos = {"direction": "long", "entry_price": 100.0, "trailing_sl_price": 101.0}
    res = evaluate_vme_exit(pos, df_15m, df_1h, current_price=106.0)

    assert res["new_trailing_sl"] == 104.50
    assert res["new_trailing_sl"] > pos["trailing_sl_price"]
    assert res["new_trailing_sl"] > 102.0  # Sobre VWAP


# ════════════════════════════════════════════════════════════
# 4. PRUEBAS DE DEFENSA DE OPCIONES (CONTRATOS CALL / PUT)
# ════════════════════════════════════════════════════════════

def test_vme_options_defense_hard_sl_and_ratchets():
    """Verifica Hard SL (-35%), Breakeven Shield (+15%) y Ratchet Tier 2 (+30%)."""
    df_15m, df_1h = _create_mock_dataframes(trend="up", price=105.0)

    # 1. Hard SL (-35%): Entrada $4.00, precio actual $2.50 (-37.5%)
    pos_hard_sl = {
        "direction": "call",
        "entry_debit": 4.00,
        "entry_price": 100.0,
        "highest_premium_seen": 4.00
    }
    res_hard_sl = evaluate_vme_exit(pos_hard_sl, df_15m, df_1h, current_price=102.0, current_option_premium=2.50)
    assert res_hard_sl["should_exit"] is True
    assert res_hard_sl["rule_code"] == "VME_EXIT_OPT_HARD_SL"

    # 2. Breakeven Shield: Pico alcanzó $4.70 (+17.5%), retrocede a $4.02
    pos_be = {
        "direction": "call",
        "entry_debit": 4.00,
        "highest_premium_seen": 4.70
    }
    res_be = evaluate_vme_exit(pos_be, df_15m, df_1h, current_price=104.0, current_option_premium=4.02)
    assert res_be["should_exit"] is True
    assert res_be["rule_code"] == "VME_EXIT_OPT_BREAKEVEN"

    # 3. Ratchet Tier 2: Pico alcanzó $5.40 (+35%), retrocede a $4.55 (bajo el piso del +15% = $4.60)
    pos_tier2 = {
        "direction": "call",
        "entry_debit": 4.00,
        "highest_premium_seen": 5.40
    }
    res_tier2 = evaluate_vme_exit(pos_tier2, df_15m, df_1h, current_price=105.0, current_option_premium=4.55)
    assert res_tier2["should_exit"] is True
    assert res_tier2["rule_code"] == "VME_EXIT_OPT_RATCHET_TIER2"
