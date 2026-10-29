"""
eTrade v7.0 — TEST SUITE: OPTIONS STRUCTURAL REGIME & EXECUTION OVERHAUL
========================================================================
Valida la integración de las 4 Reglas Maestras Símétricas (CALL & PUT),
la selección blindada de contratos (DTE 10-21d, Spread <= 5%, OI >= 100),
la custodia en 1H sin salidas prematuras por ruido en 15m,
la asignación en 3 Tranches (30%/40%/30%) para centro de costo,
y el Cooldown Dinámico de ciclo tras Stop Loss técnico.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date, datetime, timezone, timedelta
import pandas as pd
import numpy as np
import pytest

from app.core.structural_regime_engine import (
    validate_macro_1d_alignment,
    check_bollinger_reversal_trigger,
    check_ema20_pullback_trigger,
    check_structural_veto_zones,
    evaluate_structural_regime,
)
from app.options.opt_contract_picker import (
    calculate_tranche_allocation,
    calculate_3tranche_allocation,
    select_best_option_contract,
    SelectedContract,
)
from app.options.exit_engine import (
    record_options_sl_cooldown,
    is_ticker_in_options_cooldown,
    check_options_dip_rebuy_opportunity,
    evaluate_technical_rules_and_stops,
    _OPTIONS_STOPPED_OUT_COOLDOWN,
)
from app.options.autonomous_options_dispatcher import dispatch_autonomous_option_trade


# ─────────────────────────────────────────────────────────────────────────────
# 1. PRUEBAS DE LAS 4 REGLAS MAESTRAS EN STRUCTURAL REGIME ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def test_master_rule_1_trend_alignment():
    """Regla Maestra 1: CALL exige EMA3 > EMA9 > EMA20 en 1D; PUT exige EMA3 < EMA9 < EMA20."""
    bull_metrics = {"ema3": 150.0, "ema9": 145.0, "ema20": 140.0, "ema50": 130.0, "ema200": 110.0}
    bear_metrics = {"ema3": 110.0, "ema9": 115.0, "ema20": 120.0, "ema50": 130.0, "ema200": 140.0}
    mixed_metrics = {"ema3": 142.0, "ema9": 145.0, "ema20": 140.0, "ema50": 130.0, "ema200": 110.0}

    # CALL en tendencia alcista
    ok_call, msg = validate_macro_1d_alignment("CALL", bull_metrics)
    assert ok_call is True
    assert "Regla 1 CALL Válida" in msg

    # PUT en tendencia alcista (debe ser rechazado)
    ok_put_bull, _ = validate_macro_1d_alignment("PUT", bull_metrics)
    assert ok_put_bull is False

    # PUT en tendencia bajista
    ok_put, msg = validate_macro_1d_alignment("PUT", bear_metrics)
    assert ok_put is True
    assert "Regla 1 PUT Válida" in msg

    # CALL en tendencia bajista (debe ser rechazado)
    ok_call_bear, _ = validate_macro_1d_alignment("CALL", bear_metrics)
    assert ok_call_bear is False

    # Estructura mixta rechaza ambos para Regla 1
    assert validate_macro_1d_alignment("CALL", mixed_metrics)[0] is False
    assert validate_macro_1d_alignment("PUT", mixed_metrics)[0] is False


def test_master_rule_2_bollinger_reversal():
    """Regla Maestra 2: Quiebre por reversión en Bollinger (1D -> 1H)."""
    # Escenario CALL: Toca BB inferior (100.0) y 1H tiene vela verde de giro
    bb_call_metrics = {"bb_lower": 100.0, "bb_upper": 130.0, "close_1d": 99.5, "low_1d": 99.0}
    df_1h_green = pd.DataFrame({
        "open": [99.0, 99.2],
        "close": [99.3, 100.5],
        "high": [99.5, 100.8],
        "low": [98.9, 99.1]
    })
    ok_r2_call, msg_call = check_bollinger_reversal_trigger("CALL", bb_call_metrics, df_1h=df_1h_green)
    assert ok_r2_call is True
    assert "Toca BB Inferior 1D" in msg_call

    # Escenario PUT: Toca BB superior (130.0) y 1H tiene vela roja de rechazo
    bb_put_metrics = {"bb_lower": 100.0, "bb_upper": 130.0, "close_1d": 130.5, "high_1d": 131.0}
    df_1h_red = pd.DataFrame({
        "open": [130.0, 131.0],
        "close": [130.5, 129.5],
        "high": [131.2, 131.5],
        "low": [129.8, 129.2]
    })
    ok_r2_put, msg_put = check_bollinger_reversal_trigger("PUT", bb_put_metrics, df_1h=df_1h_red)
    assert ok_r2_put is True
    assert "Toca BB Superior 1D" in msg_put


def test_master_rule_3_ema20_pullback_and_retest():
    """Regla Maestra 3: Rebote o retesteo en EMA20 diaria con confirmación 1H."""
    # CALL: EMA20=120, EMA50=110 (alcista), precio en 120.5 (a 0.4% de distancia) con vela verde 1H
    metrics_call_ema20 = {"ema20": 120.0, "ema50": 110.0, "close_1d": 120.5}
    df_1h_bounce = pd.DataFrame({"open": [120.0, 120.2], "close": [120.3, 121.0]})
    ok_r3_call, msg = check_ema20_pullback_trigger("CALL", metrics_call_ema20, df_1h=df_1h_bounce)
    assert ok_r3_call is True
    assert "Soporte en EMA20 Diaria" in msg

    # PUT: EMA20=120, EMA50=130 (bajista), precio en 119.8 (retesteando por abajo) con vela roja 1H
    metrics_put_ema20 = {"ema20": 120.0, "ema50": 130.0, "close_1d": 119.8}
    df_1h_reject = pd.DataFrame({"open": [120.0, 120.1], "close": [119.8, 119.2]})
    ok_r3_put, msg = check_ema20_pullback_trigger("PUT", metrics_put_ema20, df_1h=df_1h_reject)
    assert ok_r3_put is True
    assert "Rechazo en resistencia EMA20 Diaria" in msg


def test_master_rule_4_veto_zones():
    """Regla Maestra 4: Zonas de Veto Estructural (muros de reversión y chop)."""
    # Veto CALL: precio cotiza justo bajo EMA20 (120.0) a $118.5 (-1.25%)
    metrics = {"ema20": 120.0, "ema50": 125.0, "ema200": 135.0, "bb_bandwidth_pct": 20.0}
    is_vetoed_call, v_msg = check_structural_veto_zones("CALL", metrics, current_price=118.5)
    assert is_vetoed_call is True
    assert "VETO CALL" in v_msg
    assert "inmediatamente bajo EMA20" in v_msg

    # Veto PUT: precio cotiza justo sobre EMA20 (120.0) a $121.2 (+1.0%)
    is_vetoed_put, v_msg = check_structural_veto_zones("PUT", metrics, current_price=121.2)
    assert is_vetoed_put is True
    assert "VETO PUT" in v_msg
    assert "inmediatamente sobre EMA20" in v_msg

    # Veto Deep Bear Winter para CALLs
    deep_bear_metrics = {"ema20": 80.0, "ema50": 85.0, "ema200": 120.0, "bb_bandwidth_pct": 25.0}
    is_vetoed_deep_bear, v_msg = check_structural_veto_zones("CALL", deep_bear_metrics, current_price=82.0)
    assert is_vetoed_deep_bear is True
    assert "DEEP_BEAR_WINTER" in v_msg

    # Veto por Squeeze lateral extremo (<10% bandwidth)
    chop_metrics = {"ema20": 100.0, "ema50": 100.0, "ema200": 100.0, "bb_bandwidth_pct": 7.5}
    is_vetoed_chop_c, _ = check_structural_veto_zones("CALL", chop_metrics, current_price=100.2)
    is_vetoed_chop_p, _ = check_structural_veto_zones("PUT", chop_metrics, current_price=100.2)
    assert is_vetoed_chop_c is True
    assert is_vetoed_chop_p is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. PRUEBAS DE SELECCIÓN DE CONTRATOS Y TRANCHES (DTE 10-21d, SPREAD <= 5%)
# ─────────────────────────────────────────────────────────────────────────────

def test_contract_picker_dte_and_liquidity():
    """Valida que se rechacen DTE < 10d (theta decay), spreads > 5% y OI < 100."""
    today = date(2026, 10, 28)

    sample_contracts = [
        # Contrato 1: DTE = 3 días (debe ser rechazado por DTE corto < 10)
        {
            "id": 1, "symbol": "AAPL", "right": "C", "strike": 180.0,
            "expiry": "2026-10-31",
            "opt_quotes_latest": {"bid": 2.10, "ask": 2.15, "open_interest": 500, "volume": 100, "delta": 0.50}
        },
        # Contrato 2: DTE = 7 días (debe ser rechazado por DTE < 10)
        {
            "id": 2, "symbol": "AAPL", "right": "C", "strike": 180.0,
            "expiry": "2026-11-04",
            "opt_quotes_latest": {"bid": 2.50, "ask": 2.55, "open_interest": 400, "volume": 80, "delta": 0.50}
        },
        # Contrato 3: DTE = 16 días, spread = 2.0% (válido) pero OI = 20 (poca liquidez < 100) -> rechazado
        {
            "id": 3, "symbol": "AAPL", "right": "C", "strike": 180.0,
            "expiry": "2026-11-13",
            "opt_quotes_latest": {"bid": 3.00, "ask": 3.06, "open_interest": 20, "volume": 5, "delta": 0.50}
        },
        # Contrato 4: DTE = 16 días, spread = 9.0% (> 5.0%) -> rechazado
        {
            "id": 4, "symbol": "AAPL", "right": "C", "strike": 180.0,
            "expiry": "2026-11-13",
            "opt_quotes_latest": {"bid": 3.00, "ask": 3.30, "open_interest": 600, "volume": 150, "delta": 0.50}
        },
        # Contrato 5: DTE = 16 días, spread = 2.0% (<= 5.0%), OI = 600, Vol = 150 -> ACEPTADO
        {
            "id": 5, "symbol": "AAPL", "right": "C", "strike": 180.0,
            "expiry": "2026-11-13",
            "opt_quotes_latest": {"bid": 3.00, "ask": 3.06, "open_interest": 600, "volume": 150, "delta": 0.50}
        },
    ]

    best, rejections = select_best_option_contract(
        contracts=sample_contracts,
        underlying_price=180.0,
        direction="CALL",
        now_date=today
    )

    assert best is not None
    assert best.contract_id == 5
    assert best.dte == 16
    assert best.spread_pct <= 5.0


def test_tranche_allocation_30_40_30():
    """Valida la distribución en 3 tranches: 30% Inicial, 40% Recompra 1, 30% Recompra 2."""
    # Presupuesto en dólares
    t1, t2, t3 = calculate_3tranche_allocation(1000.0)
    assert t1 == 300.0
    assert t2 == 400.0
    assert t3 == 300.0
    assert (t1 + t2 + t3) == 1000.0

    # Contratos enteros
    c_t1, c_t2, c_t3, model = calculate_tranche_allocation(10)
    assert c_t1 == 3
    assert c_t2 == 4
    assert c_t3 == 3
    assert model == "3_TRANCHES_30_40_30"

    # Con 2 contratos
    c2_t1, c2_t2, c2_t3, model2 = calculate_tranche_allocation(2)
    assert c2_t1 == 1 and c2_t2 == 1 and c2_t3 == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. PRUEBAS DE CUSTODIA EN 1H Y SIN SALIDA POR RUIDO EN 15M
# ─────────────────────────────────────────────────────────────────────────────

def test_exit_engine_1h_trend_custody():
    """
    Valida que tras 15 minutos de trade, una posición CALL NO se liquide por cruce
    bajista en 15m si la estructura macro de 1H sigue favorable (EMA3 >= EMA9 o slope > 0).
    """
    now = datetime.now(timezone.utc)
    entry_time = (now - timedelta(minutes=20)).isoformat()  # Trade age = 20 min

    position = {
        "symbol": "TSLA",
        "strategy_type": "long_call",
        "direction": "bullish",
        "qty": 1,
        "entry_time": entry_time,
        "unrealized_pnl_pct": -3.5,  # Ligera pérdida por retroceso normal
        "exit_plan": {
            "initial_sl": 190.0,
            "stop_loss_underlying": 190.0,
            "entry_underlying_price": 200.0,
        }
    }

    # Contexto técnico:
    # 15m tiene EMA3 (198.0) < EMA9 (199.0) -> Señal antigua ema_cross_15m habría liquidado aquí!
    # Pero 1H tiene EMA3 (200.0) >= EMA9 (197.0) con pendiente positiva (+0.05%) y precio ($199.5) > SL ($190.0)
    tech = {
        "valid": True,
        "symbol": "TSLA",
        "current_price": 199.5,
        "ema3_15m": 198.0,
        "ema9_15m": 199.0,
        "ema3_1h": 200.0,
        "ema9_1h": 197.0,
        "ema3_slope_1h": 0.05,
        "rsi_1h": 55.0,
    }

    should_exit, reason, data = evaluate_technical_rules_and_stops(position, tech, now)
    # DEBE MANTENER LA POSICIÓN (Custodia en 1H)
    assert should_exit is False
    assert reason is None

    # Ahora probamos que si 1H se invierte de forma irreversible (EMA3 < EMA9 y slope <= 0), SÍ liquida defensivamente
    tech_broken_1h = dict(tech)
    tech_broken_1h["ema3_1h"] = 195.0
    tech_broken_1h["ema9_1h"] = 198.0
    tech_broken_1h["ema3_slope_1h"] = -0.08

    should_exit_broken, reason_broken, _ = evaluate_technical_rules_and_stops(position, tech_broken_1h, now)
    assert should_exit_broken is True
    assert reason_broken == "trend_flip_macro_1h"


# ─────────────────────────────────────────────────────────────────────────────
# 4. PRUEBAS DE COOLDOWN DINÁMICO DE CICLO TRAS STOP LOSS
# ─────────────────────────────────────────────────────────────────────────────

def test_stop_loss_dynamic_cooldown():
    """Valida el bloqueo de un ticker mientras persista la inercia del ciclo fallido."""
    now = datetime.now(timezone.utc)
    entry_time = (now - timedelta(minutes=10)).isoformat()

    position = {
        "symbol": "NVDA",
        "strategy_type": "long_call",
        "direction": "bullish",
        "qty": 1,
        "entry_time": entry_time,
        "exit_plan": {
            "initial_sl": 120.0,
            "stop_loss_underlying": 120.0,
            "entry_underlying_price": 125.0,
        }
    }

    # El precio perfora el Stop Loss ($119.5 <= $120.0)
    tech_sl = {
        "valid": True,
        "symbol": "NVDA",
        "current_price": 119.5,
        "ema3_15m": 121.0,
        "ema9_15m": 120.5,
        "ema20_15m": 120.0,
        "ema3_1h": 122.0,
        "ema9_1h": 121.0,
    }

    should_exit, reason, _ = evaluate_technical_rules_and_stops(position, tech_sl, now)
    assert should_exit is True
    assert reason == "sl_underlying_pierced"

    # Verificar que el ticker quedó registrado en Cooldown
    assert "NVDA" in _OPTIONS_STOPPED_OUT_COOLDOWN
    assert _OPTIONS_STOPPED_OUT_COOLDOWN["NVDA"]["direction"] == "CALL"

    # Mientras el ciclo de 15m aún tenga EMA3 > EMA9 > EMA20 (la ola fallida no ha reseteado), debe bloquearse
    df_15m_still_bullish = pd.DataFrame({
        "close": [118.0] * 10 + [120.0] * 5 + [122.0] * 5  # EMA3 > EMA9 > EMA20
    })
    in_cd, cd_msg = is_ticker_in_options_cooldown("NVDA", "CALL", df_15m=df_15m_still_bullish)
    assert in_cd is True
    assert "Ciclo alcista 15m aún activo" in cd_msg

    # Cuando el ciclo resetea (velas cayendo de forma limpia y EMA3 < EMA9)
    df_15m_reset = pd.DataFrame({
        "close": [125.0] * 10 + [120.0] * 5 + [115.0] * 5  # EMA3 < EMA9
    })
    in_cd_cleared, _ = is_ticker_in_options_cooldown("NVDA", "CALL", df_15m=df_15m_reset)
    assert in_cd_cleared is False


# ─────────────────────────────────────────────────────────────────────────────
# 5. PRUEBAS DE RECOMPRA EN RETROCESO (DIP REBUYS - CENTRO DE COSTO)
# ─────────────────────────────────────────────────────────────────────────────

def test_dip_rebuy_opportunity():
    """Valida la activación de Tranche 2 (40%) y Tranche 3 (30%) en retrocesos a EMA20 con 1H alcista."""
    open_pos = {
        "status": "open",
        "direction": "bullish",
        "strategy_type": "long_call",
        "exit_plan": {
            "initial_sl": 140.0,
            "stop_loss_underlying": 140.0,
            "rebuys_count": 0,
        }
    }

    # Precio ($149.8) retrocediendo a soporte EMA20 ($150.0) a -0.13%, con 1H alcista
    tech_pullback = {
        "ema3_1h": 152.0,
        "ema9_1h": 148.0,
        "ema3_slope_1h": 0.04,
        "ema20_15m": 150.0,
        "ema20_1h": 149.5,
    }

    # Evaluar 1ra Recompra (Tranche 2 = 40%)
    rebuy_1 = check_options_dip_rebuy_opportunity(open_pos, tech_pullback, current_price=149.8)
    assert rebuy_1 is not None
    assert rebuy_1["tranche_num"] == 2
    assert rebuy_1["pct_allocation"] == 0.40

    # Simular que se ejecutó Tranche 2 y ahora rebuys_count = 1
    open_pos["exit_plan"]["rebuys_count"] = 1
    rebuy_2 = check_options_dip_rebuy_opportunity(open_pos, tech_pullback, current_price=149.8)
    assert rebuy_2 is not None
    assert rebuy_2["tranche_num"] == 3
    assert rebuy_2["pct_allocation"] == 0.30

    # Simular que se ejecutaron las 3 compras (rebuys_count = 2) -> No permite más
    open_pos["exit_plan"]["rebuys_count"] = 2
    rebuy_3 = check_options_dip_rebuy_opportunity(open_pos, tech_pullback, current_price=149.8)
    assert rebuy_3 is None
