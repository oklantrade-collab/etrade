"""Tests Plan v2 blindaje de Opciones: EOD Profit Harvest, Mid-Market, TP sin techo, preferencia suave tardia."""
from datetime import datetime, timezone

from app.options import exit_engine as ee
from app.options import market_calendar as mc
from app.options import paper_execution as pe
from app.options import settings_defaults as sd
from app.options.portfolio_selector import select_portfolio

# Jueves 2026-11-12 (sesion regular, cierre 16:00 ET = 21:00 UTC)
T_1405 = datetime(2026, 11, 12, 19, 5, tzinfo=timezone.utc)    # 14:05 ET (115 min al cierre)
T_1430 = datetime(2026, 11, 12, 19, 30, tzinfo=timezone.utc)   # 14:30 ET (90 min al cierre)
T_1505 = datetime(2026, 11, 12, 20, 5, tzinfo=timezone.utc)    # 15:05 ET (55 min al cierre)
T_1555 = datetime(2026, 11, 12, 20, 55, tzinfo=timezone.utc)   # 15:55 ET (5 min al cierre)
T_SAT = datetime(2026, 11, 14, 20, 5, tzinfo=timezone.utc)     # sabado


def test_settings_defaults_incluyen_nuevos_parametros():
    d = sd.default_settings()
    assert d["eod_profit_lock_enabled"] is True
    assert d["eod_profit_lock_minutes_before"] == 60
    assert d["eod_profit_lock_min_pnl_pct"] == 2.0
    assert d["use_mid_pricing"] is True
    assert d["long_tp_uncapped"] is True
    assert sd.validate_cross_rules(d) == []


def test_minutes_to_close():
    assert round(mc.minutes_to_close(T_1505)) == 55
    assert mc.minutes_to_close(T_SAT) is None


def test_eod_cosecha_con_ganancia_en_ultima_hora():
    ok, why = ee.should_exit_eod_profit_harvest(40.0, 4.0, T_1505)
    assert ok and "EOD Profit Harvest" in why
    ok, _ = ee.should_exit_eod_profit_harvest(40.0, 4.0, T_1555)
    assert ok


def test_eod_no_cosecha_fuera_de_ultima_hora_ni_sin_umbral_ni_en_perdida():
    assert ee.should_exit_eod_profit_harvest(40.0, 4.0, T_1430)[0] is False   # antes de 15:00 ET
    assert ee.should_exit_eod_profit_harvest(10.0, 1.0, T_1505)[0] is False   # bajo +2%
    assert ee.should_exit_eod_profit_harvest(-20.0, -3.0, T_1505)[0] is False  # en perdida
    assert ee.should_exit_eod_profit_harvest(40.0, 4.0, T_SAT)[0] is False    # sin sesion


def test_eod_respeta_flag_deshabilitado():
    eff = sd.default_settings()
    eff["eod_profit_lock_enabled"] = False
    assert ee.should_exit_eod_profit_harvest(40.0, 4.0, T_1505, eff)[0] is False


def _long_call_position(entry=4.0, qty=1):
    return {
        "strategy_type": "long_call",
        "qty": qty,
        "entry_debit": entry,
        "entry_total_invested": entry * 100 * qty + 1.4 * qty,
        "entry_fills": [{"conid": 1, "side": "buy", "strike": 100.0, "right": "C"}],
        "expiry": "2026-11-20",
        "exit_plan": {},
    }


def test_mark_to_market_usa_mid_y_no_nace_en_perdida():
    pos = _long_call_position(entry=4.05)
    quotes = {1: {"bid": 3.80, "ask": 4.20}}  # spread ~10%
    eff = sd.default_settings()
    mark_mid = pe.mark_position_to_market(pos, quotes, eff)
    eff_bid = dict(eff, use_mid_pricing=False)
    mark_bid = pe.mark_position_to_market(pos, quotes, eff_bid)
    assert mark_mid["valid"] and mark_bid["valid"]
    assert mark_mid["unrealized_pnl"] > mark_bid["unrealized_pnl"]
    assert mark_mid["unrealized_pnl_pct"] > -5.0   # solo comisiones, no el spread completo


def test_evaluate_position_exit_cosecha_eod(monkeypatch):
    monkeypatch.setattr("app.core.market_hours.is_options_market_open", lambda *a, **k: (True, "ok"))
    pos = _long_call_position(entry=4.0)
    quotes = {1: {"bid": 4.30, "ask": 4.50}}  # mid 4.40 -> +10%
    eff = sd.default_settings()
    should, reason, info = ee.evaluate_position_exit(pos, quotes, {}, eff, now=T_1505, tech_context=None)
    assert should and reason == "opt_eod_profit_harvest"
    assert ee.DB_EXIT_REASONS_MAP[reason] == "take_profit"
    # Antes de la ultima hora no cosecha por EOD
    should2, reason2, _ = ee.evaluate_position_exit(pos, quotes, {}, eff, now=T_1430, tech_context=None)
    assert reason2 != "opt_eod_profit_harvest"


def test_tp_sin_techo_con_contexto_tecnico(monkeypatch):
    monkeypatch.setattr("app.core.market_hours.is_options_market_open", lambda *a, **k: (True, "ok"))
    pos = _long_call_position(entry=4.0)
    quotes = {1: {"bid": 7.40, "ask": 7.60}}  # +87% (supera el +75% fijo)
    eff = sd.default_settings()
    tech_ok = {"valid": True, "current_price": 100.0}
    should, reason, _ = ee.evaluate_position_exit(pos, quotes, {}, eff, now=T_1430, tech_context=tech_ok)
    assert reason != "take_profit"   # sin techo: no se corta por el +75% fijo
    # Sin contexto tecnico se conserva el TP de respaldo
    should_b, reason_b, _ = ee.evaluate_position_exit(pos, quotes, {}, eff, now=T_1430, tech_context=None)
    assert should_b and reason_b == "take_profit"


def _cand(score):
    return {
        "id": 1, "underlying_id": 1, "direction": "bullish", "sector": "Tech", "expiry": "2026-11-20",
        "score": score, "max_loss_total": 300.0, "max_loss_contract": 300.0, "qty": 1,
        "eligibility_status": "eligible",
    }


def test_preferencia_suave_tardia_sube_min_score_sin_bloquear():
    eff = sd.default_settings()  # min_score 45 (+10 en la ultima hora)
    eff["_now_override"] = T_1505
    res_late = select_portfolio([_cand(50.0)], [], eff)
    assert any("inferior al minimo" in str(s.get("reason")) for s in res_late.skipped)
    eff2 = sd.default_settings()
    eff2["_now_override"] = T_1430
    res_early = select_portfolio([_cand(50.0)], [], eff2)
    assert not any("inferior al minimo" in str(s.get("reason")) for s in res_early.skipped)
    # Un score alto SIGUE pudiendo entrar de tarde (no hay bloqueo)
    eff3 = sd.default_settings()
    eff3["_now_override"] = T_1505
    res_late_high = select_portfolio([_cand(70.0)], [], eff3)
    assert not any("inferior al minimo" in str(s.get("reason")) for s in res_late_high.skipped)
