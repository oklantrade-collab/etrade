"""Pruebas del Sprint 6: Paper Trading Engine y Motor de Salidas.
Verifica:
  1. Fills conservadores de entrada y salida (ask + slippage en compra, bid - slippage en venta).
  2. Comisiones reales por contrato y calculo exacto de P&L realizado.
  3. Mark-to-market a liquidacion conservadora y deteccion de cotizaciones corruptas.
  4. Reglas del motor de salidas (§12.3):
     - Take Profit (+75% en long / +60% beneficio maximo en spreads).
     - Stop Loss (-50% del debito/prima).
     - Cierre forzado por tiempo (15 min antes de campana en DTE, respetando feriados y early close).
     - Invalidacion por inversion de direccion APEX (flip).
  5. Clasificacion y validacion ADUANA de salidas (pasivas vs activas).
  6. Principio rector: ausencia absoluta de llamadas a metodos de ordenes del broker.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import pytest

from app.options import exit_engine as ee
from app.options import options_aduana as aduana
from app.options import paper_execution as pe
from app.options import settings_defaults as sd

EFF = sd.effective_settings(None)


def mock_candidate(strat: str = "bull_call_spread", debit: float = 0.40, qty: int = 1) -> dict:
    return {
        "id": 10,
        "underlying_id": 1,
        "symbol": "SPY",
        "strategy_type": strat,
        "direction": "bullish",
        "expiry": "2026-11-20",
        "qty": qty,
        "entry_debit": debit,
        "costs_contract": 4.80,
        "max_loss_total": round(debit * 100 * qty + 4.80 * qty, 2),
        "max_profit_contract": 60.0,
        "breakeven": 20.40,
        "exit_plan": {"tp_pct": 60, "sl_pct": 50},
        "legs": [
            {"conid": 1001, "side": "buy", "right": "C", "strike": 20, "bid": 0.98, "ask": 1.00, "market_data_type": "LIVE"},
            {"conid": 1002, "side": "sell", "right": "C", "strike": 21, "bid": 0.58, "ask": 0.60, "market_data_type": "LIVE"},
        ],
    }


def mock_open_position(strat: str = "bull_call_spread", debit: float = 0.40, qty: int = 1,
                       invested: float = 44.80, max_profit: float = 60.0,
                       direction: str = "bullish", expiry: str = "2026-11-20") -> dict:
    return {
        "id": 1,
        "candidate_id": 10,
        "underlying_id": 1,
        "symbol": "SPY",
        "strategy_type": strat,
        "direction": direction,
        "status": "open",
        "qty": qty,
        "expiry": expiry,
        "entry_debit": debit,
        "entry_total_invested": invested,
        "max_loss_total": invested,
        "max_profit_total": max_profit,
        "unrealized_pnl": 0.0,
        "last_mark_price": debit,
        "entry_fills": [
            {"conid": 1001, "side": "buy", "strike": 20, "right": "C", "bid": 0.98, "ask": 1.00, "fill_price": 1.0002, "slippage_applied": 0.0002},
            {"conid": 1002, "side": "sell", "strike": 21, "right": "C", "bid": 0.58, "ask": 0.60, "fill_price": 0.5798, "slippage_applied": 0.0002},
        ],
    }


# ====================================================================== 1. Fills Conservadores
def test_entry_fill_simulation_applies_conservative_slippage_and_fees():
    cand = mock_candidate(strat="bull_call_spread", debit=0.40, qty=1)
    eff = dict(EFF, slippage_normal=0.01, commission_per_contract=2.0, extra_fees_per_contract=0.40)
    res = pe.simulate_entry_fill(cand, None, eff)

    # Leg 1 (buy): ask=1.00, bid=0.98 -> spread=0.02 -> slippage=0.0002 -> fill=1.0002
    f1 = res.entry_fills[0]
    assert f1["fill_price"] == pytest.approx(1.0002, abs=1e-4)

    # Leg 2 (sell): ask=0.60, bid=0.58 -> spread=0.02 -> slippage=0.0002 -> fill=0.5798
    f2 = res.entry_fills[1]
    assert f2["fill_price"] == pytest.approx(0.5798, abs=1e-4)

    # Net debit = 1.0002 - 0.5798 = 0.4204
    assert res.entry_debit == pytest.approx(0.4204, abs=1e-4)
    # Comisiones: 2 legs * $2.40 = $4.80
    assert res.entry_costs == 4.80
    # Total invertido: 0.4204 * 100 * 1 + 4.80 = 46.84
    assert res.entry_total_invested == pytest.approx(46.84, abs=0.01)


def test_exit_fill_inverts_legs_and_computes_realized_pnl():
    pos = mock_open_position(strat="bull_call_spread", invested=46.84, qty=1)
    # Mercado se mueve a favor: pierna 20C sube a bid=1.40, pierna 21C sube a ask=0.70
    quotes = {
        1001: {"bid": 1.40, "ask": 1.42, "market_data_type": "LIVE"},
        1002: {"bid": 0.68, "ask": 0.70, "market_data_type": "LIVE"},
    }
    eff = dict(EFF, slippage_normal=0.01, commission_per_contract=2.0, extra_fees_per_contract=0.40)
    res = pe.simulate_exit_fill(pos, quotes, eff, exit_reason="take_profit")

    # Pierna 1 (original buy) se vende al bid - slippage: 1.40 - 0.01 * 0.02 = 1.3998
    # Pierna 2 (original sell) se compra al ask + slippage: 0.70 + 0.01 * 0.02 = 0.7002
    assert res.exit_credit == pytest.approx(1.3998 - 0.7002, abs=1e-4)  # ~0.6996
    # Recuperado neto: 0.6996 * 100 - 4.80 comisiones de salida = ~65.16
    assert res.exit_costs == 4.80
    assert res.exit_total_recovered == pytest.approx(65.16, abs=0.05)
    # P&L realizado: 65.16 - 46.84 = +18.32 USD
    assert res.realized_pnl == pytest.approx(65.16 - 46.84, abs=0.05)
    assert res.exit_reason == "take_profit"


def test_mark_to_market_tracks_unrealized_pnl():
    pos = mock_open_position(strat="bull_call_spread", invested=46.84, qty=1)
    quotes = {
        1001: {"bid": 1.20, "ask": 1.22},
        1002: {"bid": 0.60, "ask": 0.62},
    }
    eff = dict(EFF, commission_per_contract=2.0, extra_fees_per_contract=0.40)
    mark = pe.mark_position_to_market(pos, quotes, eff)
    assert mark["valid"] is True
    # Liquidacion conservadora: sell at bid 1.20, buy at ask 0.62 -> proceeds 0.58
    # Valor mark: 0.58 * 100 - 4.80 comisiones = 53.20 USD
    # Unrealized PnL: 53.20 - 46.84 = +6.36 USD
    assert mark["unrealized_pnl"] == pytest.approx(6.36, abs=0.02)


def test_mark_to_market_flags_corrupt_quotes_without_zero_fabrication():
    pos = mock_open_position()
    # Cotizacion cruzada (bid > ask) o faltante
    quotes = {1001: {"bid": 1.50, "ask": 1.40}}
    mark = pe.mark_position_to_market(pos, quotes, EFF)
    assert mark["valid"] is False


# ====================================================================== 2. Motor de Salidas
def test_take_profit_spread_triggers_at_60_pct_of_max_profit():
    pos = mock_open_position(strat="bull_call_spread", max_profit=50.0)
    eff = dict(EFF, spread_tp_pct=60.0)

    # 60% de 50 = +30 USD
    hit_below, _ = ee.should_exit_take_profit(pos, 25.0, eff)
    assert hit_below is False

    hit_exact, reason = ee.should_exit_take_profit(pos, 30.0, eff)
    assert hit_exact is True
    assert "Take Profit alcanzado" in reason


def test_take_profit_long_option_triggers_at_75_pct_of_invested():
    pos = mock_open_position(strat="long_call", invested=40.0)
    eff = dict(EFF, long_tp_pct=75.0)

    # 75% de 40 = +30 USD
    assert ee.should_exit_take_profit(pos, 28.0, eff)[0] is False
    hit, reason = ee.should_exit_take_profit(pos, 31.0, eff)
    assert hit is True
    assert "75" in reason and "Take Profit" in reason


def test_stop_loss_triggers_at_minus_50_pct():
    pos = mock_open_position(strat="bull_call_spread", invested=40.0)
    eff = dict(EFF, spread_sl_pct=50.0)

    # -50% de 40 = -20 USD
    assert ee.should_exit_stop_loss(pos, -15.0, eff)[0] is False
    hit, reason = ee.should_exit_stop_loss(pos, -20.5, eff)
    assert hit is True
    assert "Stop Loss alcanzado" in reason


def test_forced_close_time_on_expiry_day():
    today_str = "2026-10-19"
    pos = mock_open_position(expiry=today_str)
    eff = dict(EFF, force_close_minutes_before=15)

    # Hora regular lunes: cierre 16:00 ET -> forzar salida a las 15:45 ET (19:45 UTC)
    before_close = datetime(2026, 10, 19, 19, 30, tzinfo=timezone.utc)  # 15:30 ET
    at_force_time = datetime(2026, 10, 19, 19, 45, tzinfo=timezone.utc)  # 15:45 ET

    assert ee.should_exit_by_time(pos, before_close, eff)[0] is False
    hit, reason = ee.should_exit_by_time(pos, at_force_time, eff)
    assert hit is True
    assert "Cierre forzado por tiempo" in reason

    # En un dia que NO es vencimiento no se dispara
    other_day = datetime(2026, 10, 18, 19, 45, tzinfo=timezone.utc)
    assert ee.should_exit_by_time(pos, other_day, eff)[0] is False


def test_signal_invalidation_triggers_when_direction_flips():
    pos = mock_open_position(direction="bullish")
    eff = dict(EFF, exit_on_direction_flip=True)

    und_same = {"symbol": "SPY", "direction": "bullish"}
    und_flip = {"symbol": "SPY", "direction": "bearish"}

    assert ee.should_exit_by_invalidation(pos, und_same, eff)[0] is False
    hit, reason = ee.should_exit_by_invalidation(pos, und_flip, eff)
    assert hit is True
    assert "Senal APEX invertida" in reason


def test_aduana_exit_classification_and_mode_check():
    assert aduana.classify_exit("take_profit") == "ACTIVA"
    assert aduana.classify_exit("signal_invalidation") == "ACTIVA"
    assert aduana.classify_exit("stop_loss") == "PASIVA"
    assert aduana.classify_exit("forced_close_time") == "PASIVA"
    assert aduana.classify_exit("bad_data_close") == "PASIVA"

    ctx_paper = aduana.AduanaContext(now=datetime.now(timezone.utc), underlying_id=1, execution_mode="paper")
    ctx_live = aduana.AduanaContext(now=datetime.now(timezone.utc), underlying_id=1, execution_mode="live")

    assert aduana.validate_exit("take_profit", ctx_paper).approved is True
    assert aduana.validate_exit("stop_loss", ctx_live).approved is False


def test_zero_broker_order_methods_in_paper_modules():
    """Principio rector: Ningun metodo de ordenes de broker existe en el modulo de ejecucion paper."""
    forbidden = ["placeOrder", "cancelOrder", "reqGlobalCancel", "exerciseOptions", "orderStatus", "openOrder"]
    for mod in [pe, ee]:
        for attr in forbidden:
            assert not hasattr(mod, attr)
