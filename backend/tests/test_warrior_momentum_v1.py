"""
test_warrior_momentum_v1.py — Test Suite for RP_WARRIOR_MOMENTUM_V1 & Evaluators
==============================================================================
Valida la integridad inmutable del Rule Pack, los 4 evaluadores lógicos
de Ross Cameron y el endpoint /api/eti/v1/context.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.stocks.warrior_momentum_engine import (
    WarriorRulePackManager,
    TickerMetrics,
    Candle,
    ActiveTrade,
    DailySession,
    evaluate_screener,
    evaluate_bull_flag_trigger,
    evaluate_position_lifecycle,
    check_safety_guardrails,
    build_warrior_signal
)

client = TestClient(app)


# =====================================================================
# 1. TEST DE INTEGRIDAD DEL RULE PACK Y HASH SHA-256
# =====================================================================

def test_rule_pack_immutable_integrity():
    mgr = WarriorRulePackManager.get_instance()
    context = mgr.get_context()

    assert context.get("rule_pack_id") == "RP_WARRIOR_MOMENTUM_V1"
    assert context.get("version") == "1.0.0"
    assert mgr.hash_sha256 == "e8d19fbc746830d55e8841a0e1c2579b8a3e792c019d3851aaa7c93e4bf18290e2"
    assert mgr.is_verified is True
    assert len(mgr.rules) == 4

    codes = [r["rule_code"] for r in mgr.rules]
    assert "RP_WARRIOR_01_HOD_MOMENTUM_BREAK" in codes
    assert "RP_WARRIOR_04_MICRO_PULLBACK_EMA9" in codes
    assert "RP_WARRIOR_08_SMALL_ACCOUNT_COMPOUNDING" in codes
    assert "RP_WARRIOR_03_CUSHION_TRADE_SIZING" in codes


# =====================================================================
# 2. TEST REGLA A: SCREENER FILTER GATE
# =====================================================================

def test_screener_valid_asset():
    valid = TickerMetrics(
        symbol="SMFL",
        price=4.25,
        floatShares=8_500_000,
        relativeVolume=6.8,
        premarketVolume=850_000,
        hasBreakingNews=True,
        bidAskSpread=0.03
    )
    assert evaluate_screener(valid) is True


def test_screener_rejections():
    # 1. Precio fuera de rango (> $20.0 hard ceiling)
    too_expensive = TickerMetrics(
        symbol="BIG",
        price=24.50,
        floatShares=5_000_000,
        relativeVolume=8.0,
        premarketVolume=1_000_000,
        hasBreakingNews=True
    )
    assert evaluate_screener(too_expensive) is False

    # 2. Float excesivo (> 20M)
    high_float = TickerMetrics(
        symbol="DILUTED",
        price=5.0,
        floatShares=45_000_000,
        relativeVolume=10.0,
        premarketVolume=2_000_000,
        hasBreakingNews=True
    )
    assert evaluate_screener(high_float) is False

    # 3. RVOL insuficiente (< 5.0)
    low_rvol = TickerMetrics(
        symbol="QUIET",
        price=3.50,
        floatShares=4_000_000,
        relativeVolume=2.2,
        premarketVolume=100_000,
        hasBreakingNews=True
    )
    assert evaluate_screener(low_rvol) is False

    # 4. Sin noticia / catalizador
    no_news = TickerMetrics(
        symbol="PUMP",
        price=4.00,
        floatShares=3_000_000,
        relativeVolume=8.0,
        premarketVolume=900_000,
        hasBreakingNews=False
    )
    assert evaluate_screener(no_news) is False

    # 5. Spread excesivo
    wide_spread = TickerMetrics(
        symbol="WIDE",
        price=3.00,
        floatShares=2_000_000,
        relativeVolume=7.0,
        premarketVolume=600_000,
        hasBreakingNews=True,
        bidAskSpread=0.18
    )
    assert evaluate_screener(wide_spread) is False


# =====================================================================
# 3. TEST REGLA B: BULL FLAG & FIRST CANDLE NEW HIGH
# =====================================================================

def test_bull_flag_trigger_success():
    # Velas de 1 minuto:
    # 1. Vela base
    c1 = Candle(open=4.00, high=4.10, low=3.95, close=4.05, volume=30_000)
    # 2. Vela Mástil (Pole) explosiva: de 4.00 a 4.50 (altura: $0.50)
    pole = Candle(open=4.05, high=4.50, low=4.00, close=4.48, volume=120_000)
    # 3. Vela Pullback roja: retroceso a 4.35 (depth = 4.50 - 4.35 = 0.15 -> 30% del mástil, sano <= 50%)
    pullback = Candle(open=4.48, high=4.45, low=4.35, close=4.38, volume=40_000)
    # 4. Vela actual consolidando sobre EMA9/VWAP
    current = Candle(open=4.38, high=4.45, low=4.36, close=4.42, volume=25_000)

    candles = [c1, pole, pullback, current]

    vwap = 4.25
    ema9 = 4.32
    current_tick = 4.46  # Supera el high de la vela previa (4.45)

    res = evaluate_bull_flag_trigger(
        candles_1m=candles,
        current_tick_price=current_tick,
        vwap=vwap,
        ema9=ema9
    )

    assert res.triggered is True
    assert res.vwap_condition_met is True
    assert res.ema9_condition_met is True
    assert res.volume_decay_met is True
    assert res.underlying_trigger_price == 4.45
    assert res.initial_technical_stop == 4.35
    assert res.risk_cents_per_share == 0.10


def test_bull_flag_rejections():
    c1 = Candle(open=4.00, high=4.10, low=3.95, close=4.05, volume=30_000)
    # Mástil: 4.00 a 4.50
    pole = Candle(open=4.05, high=4.50, low=4.00, close=4.48, volume=120_000)
    # Pullback demasiado profundo (> 50% de 0.50 -> cae a 4.15 = 0.35 / 0.50 = 70%)
    deep_pullback = Candle(open=4.48, high=4.35, low=4.15, close=4.18, volume=40_000)
    current = Candle(open=4.18, high=4.25, low=4.16, close=4.22, volume=25_000)

    res = evaluate_bull_flag_trigger(
        candles_1m=[c1, pole, deep_pullback, current],
        current_tick_price=4.36,
        vwap=4.25,
        ema9=4.30
    )
    assert res.triggered is False
    assert "PULLBACK_TOO_DEEP" in res.reason


# =====================================================================
# 4. TEST REGLA C: GESTIÓN DE SALIDA (PAY THE TRADER + BREAKEVEN)
# =====================================================================

def test_position_lifecycle_tp1_and_breakeven():
    trade = ActiveTrade(
        trade_id="TR_001",
        symbol="SMFL",
        entry_price=4.25,
        shares=1000,
        tp1_executed=False,
        initial_technical_stop=4.14,
        stop_loss=4.14,
        current_ema9=4.28,
        last_1m_close=4.38
    )

    # El precio sube a $4.40 (+$0.15 de ganancia)
    current_bid = 4.40
    actions = evaluate_position_lifecycle(trade, current_bid=current_bid)

    assert len(actions) == 2
    assert actions[0].action == "SELL_PARTIAL"
    assert actions[0].size_pct == 50.0
    assert actions[0].order_type == "ASK_LIMIT"

    assert actions[1].action == "UPDATE_STOP_LOSS"
    assert actions[1].new_stop_price == 4.26  # entry_price + 0.01


def test_position_lifecycle_technical_stop():
    trade = ActiveTrade(
        trade_id="TR_002",
        symbol="SMFL",
        entry_price=4.25,
        shares=500,
        tp1_executed=False,
        initial_technical_stop=4.14,
        stop_loss=4.14,
        current_ema9=4.22,
        last_1m_close=4.20
    )

    # El precio cae al mínimo de la vela de entrada ($4.14)
    current_bid = 4.14
    actions = evaluate_position_lifecycle(trade, current_bid=current_bid)

    assert len(actions) == 1
    assert actions[0].action == "CLOSE_ALL"
    assert actions[0].order_type == "MARKET_PROTECTED"


def test_position_lifecycle_runner_exit_on_ema9_loss():
    # Ya cobró TP1, le queda el 50% de runner
    trade = ActiveTrade(
        trade_id="TR_003",
        symbol="SMFL",
        entry_price=4.25,
        shares=500,
        tp1_executed=True,
        initial_technical_stop=4.14,
        stop_loss=4.26,
        current_ema9=4.55,
        last_1m_close=4.51  # Cierra bajo la EMA 9
    )

    current_bid = 4.52
    actions = evaluate_position_lifecycle(trade, current_bid=current_bid)

    assert len(actions) == 1
    assert actions[0].action == "CLOSE_ALL"
    assert actions[0].order_type == "BID_LIMIT"
    assert actions[0].reason == "RUNNER_EXIT_1M_CLOSED_BELOW_EMA9"


# =====================================================================
# 5. TEST REGLA D: SAFETY GUARDRAILS (CIRCUIT BREAKERS)
# =====================================================================

def test_guardrails_consecutive_losses():
    session = DailySession(consecutive_losses=2, realized_pnl_usd=-60.0, current_time_est="09:50")
    allowed = check_safety_guardrails(session)

    assert allowed is False
    assert session.trading_blocked is True
    assert session.block_reason == "CIRCUIT_BREAKER_2_CONSECUTIVE_LOSSES"


def test_guardrails_max_daily_loss():
    session = DailySession(consecutive_losses=1, realized_pnl_usd=-155.0, current_time_est="10:05")
    allowed = check_safety_guardrails(session)

    assert allowed is False
    assert session.trading_blocked is True
    assert session.block_reason == "MAX_DAILY_LOSS_REACHED"


def test_guardrails_time_window_past_11():
    session = DailySession(consecutive_losses=0, realized_pnl_usd=250.0, current_time_est="11:05")
    allowed = check_safety_guardrails(session)

    assert allowed is False
    assert session.trading_blocked is True
    assert session.block_reason == "OUTSIDE_MOMENTUM_WINDOW"


def test_guardrails_healthy_session():
    session = DailySession(consecutive_losses=1, realized_pnl_usd=80.0, current_time_est="09:45")
    allowed = check_safety_guardrails(session)

    assert allowed is True
    assert session.trading_blocked is False


# =====================================================================
# 6. TEST DE LA SEÑAL CANÓNICA (ETISignalPayload)
# =====================================================================

def test_build_warrior_signal():
    sig = build_warrior_signal(
        symbol="SMFL",
        trigger_price=4.25,
        technical_stop=4.14,
        relative_volume=6.8,
        account_tier="base_tier_usd_2000"
    )

    assert sig.symbol == "SMFL"
    assert sig.strategy.horizon == "SCALPING"
    assert sig.strategy.playbook_rule == "RP_WARRIOR_08_SMALL_ACCOUNT_COMPOUNDING"
    assert sig.technical_gate.trigger_type == "FIRST_1M_CANDLE_NEW_HIGH"
    assert sig.technical_gate.underlying_trigger_price == 4.25
    assert sig.risk_management.entry_price == 4.25
    assert sig.risk_management.initial_stop_loss == 4.14
    assert sig.risk_management.tp1_target == 4.40
    assert sig.risk_management.tp1_partial_pct == 50.0
    assert sig.risk_management.breakeven_on_tp1 is True
    assert sig.risk_management.max_account_risk_usd == 50.0


# =====================================================================
# 7. TEST DEL ENDPOINT /api/eti/v1/context
# =====================================================================

def test_endpoint_get_context():
    resp = client.get("/api/eti/v1/context")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["is_verified"] is True
    assert data["hash_sha256"] == "e8d19fbc746830d55e8841a0e1c2579b8a3e792c019d3851aaa7c93e4bf18290e2"
    assert data["data"]["rule_pack_id"] == "RP_WARRIOR_MOMENTUM_V1"


def test_endpoint_get_rules():
    resp = client.get("/api/eti/v1/context/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 4


def test_endpoint_evaluate_screener():
    payload = {
        "symbol": "SMFL",
        "price": 4.25,
        "floatShares": 8500000,
        "relativeVolume": 6.8,
        "premarketVolume": 850000,
        "hasBreakingNews": True,
        "bidAskSpread": 0.03
    }
    resp = client.post("/api/eti/v1/context/evaluate/screener", json=payload)
    assert resp.status_code == 200
    assert resp.json()["is_tradable"] is True
