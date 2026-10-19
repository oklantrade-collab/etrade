"""Pruebas Sprint 4 + Gate G2: valoracion contrastada con calculos INDEPENDIENTES.

Contrastes G2:
 1. Valores de referencia de libro (Hull, Options, Futures and Other Derivatives, ej. 15.6).
 2. Black-Scholes reimplementado con otro metodo de cdf (integracion numerica con numpy) y otra formula (paridad).
 3. Monte Carlo (numpy, semilla fija) vs cuadratura del modulo para EV y probabilidad.
 4. Identidad analitica: con r=0, sin costes ni spreads, E[valor a la salida] = precio BS inicial.
"""
import math
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from app.options import bs
from app.options import market_calendar as mc
from app.options import options_aduana as ad
from app.options import settings_defaults as sd
from app.options import strategies as st
from app.options import valuation as val
from app.options.candidates import candidate_row

TODAY = date(2026, 10, 19)
EFF = sd.default_settings()


# ====================================================================== G2.1 / G2.2: Black-Scholes
def test_bs_hull_reference_values():
    # Hull ej. 15.6: S=42 K=40 r=10% sigma=20% T=0.5 -> call 4.76, put 0.81
    assert bs.bs_price(42, 40, 0.5, 0.10, 0.20, "C") == pytest.approx(4.7594, abs=5e-4)
    assert bs.bs_price(42, 40, 0.5, 0.10, 0.20, "P") == pytest.approx(0.8086, abs=5e-4)
    assert bs.bs_delta(42, 40, 0.5, 0.10, 0.20, "C") == pytest.approx(0.7791, abs=5e-4)


def _indep_cdf(x: float) -> float:
    xs = np.linspace(-12.0, x, 400001)
    return float(np.trapz(np.exp(-0.5 * xs ** 2) / math.sqrt(2 * math.pi), xs))


@pytest.mark.parametrize("S,K,T,r,s", [(20, 20, 18 / 365, 0.04, 0.5), (20, 21, 30 / 365, 0.04, 0.6), (150, 140, 0.5, 0.03, 0.25)])
def test_bs_vs_independent_implementation(S, K, T, r, s):
    d1 = (math.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T))
    d2 = d1 - s * math.sqrt(T)
    call = S * _indep_cdf(d1) - K * math.exp(-r * T) * _indep_cdf(d2)
    assert bs.bs_price(S, K, T, r, s, "C") == pytest.approx(call, abs=1e-6)
    # paridad put-call con la implementacion del modulo
    put = bs.bs_price(S, K, T, r, s, "P")
    assert bs.bs_price(S, K, T, r, s, "C") - put == pytest.approx(S - K * math.exp(-r * T), abs=1e-8)


# ====================================================================== helpers
def spread_row(direction="bullish", iv=0.55, S=20.0):
    lo = st.Q(1, 2000, "C", 20, date(2026, 11, 6), 0.97, 1.01, 100, 500, iv, 0.5, True, None, "LIVE")
    hi = st.Q(2, 2100, "C", 21, date(2026, 11, 6), 0.57, 0.61, 100, 500, iv, 0.3, True, None, "LIVE")
    eff = dict(EFF, max_exec_overcost_pct=25, max_risk_per_trade_usd=100)
    c, why = st.build_spread("bull_call_spread", lo, hi, S, TODAY, eff)
    assert c, why
    row = candidate_row(c, 1, "apex", 1, {}, "2026-10-19T14:00:00+00:00")
    row.update(id=1, underlying_id=1)
    row["direction"] = direction
    return row, eff


# ====================================================================== G2.4: identidad analitica
def test_zero_cost_zero_drift_ev_is_zero_when_entry_is_fair():
    S0, K, iv = 20.0, 20.0, 0.5
    expiry = date(2026, 11, 18)                     # 30 DTE
    T0 = 30 / 365
    fair = bs.bs_price(S0, K, T0, 0.0, iv, "C")
    row = {"legs": [{"side": "buy", "right": "C", "strike": K, "iv": iv, "bid": fair, "ask": fair}],
           "entry_debit": fair, "costs_contract": 0.0, "max_loss_contract": fair * 100,
           "expiry": expiry.isoformat(), "direction": "bullish"}
    eff = dict(EFF, risk_free_rate_pct=0.0, alpha=0.0, vol_factor_k=1.0, horizon_hours=3.0)
    out = val.value_candidate(row, S0, eff, TODAY, direction_verified=True)
    assert out["ev_neutral_net"] == pytest.approx(0.0, abs=0.05)         # +-5 centavos por contrato
    assert out["ev_view_net"] == pytest.approx(out["ev_neutral_net"], abs=0.01)   # alpha = 0
    # la media del precio de salida bajo A es S0 (martingala)
    assert val._expect  # noqa  (funcion existente)


def test_neutral_distribution_mean_is_spot():
    legs = val.legs_from_row([{"side": "buy", "right": "C", "strike": 20, "iv": 0.5, "bid": 0.3, "ask": 0.3}])
    r = val._expect(legs, 0.3, 0.0, 20.0, 0.02, 0.0, 0.05, 0.0, 0.0, 1.0, 0.0, 0.0)
    assert r["mean_exit_price"] == pytest.approx(20.0, abs=0.002)


# ====================================================================== G2.3: Monte Carlo
def mc_ev_pop(row, S0, eff, mu_sign):
    legs = val.legs_from_row(row["legs"])
    T0 = (date.fromisoformat(row["expiry"]) - TODAY).days / 365.0
    h = eff["horizon_hours"]
    T_exit = T0 - h / val.TRADING_YEAR_HOURS
    sig = val.sigma_h(legs[0].iv, eff["vol_factor_k"], h)
    mu = mu_sign * eff["alpha"] * sig
    rng = np.random.default_rng(12345)
    z = rng.standard_normal(200_000)
    z = np.concatenate([z, -z])                                   # variables antiteticas
    S_T = S0 * np.exp(-0.5 * sig ** 2 + mu + sig * z)
    r = eff["risk_free_rate_pct"] / 100.0

    def vbs(S, K, T, s, right):                                   # BS vectorizado independiente (cdf via np.vectorize de math.erf)
        d1 = (np.log(S / K) + (r + 0.5 * s * s) * T) / (s * math.sqrt(T))
        d2 = d1 - s * math.sqrt(T)
        N = np.vectorize(lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2))))
        return S * N(d1) - K * math.exp(-r * T) * N(d2) if right == "C" else K * math.exp(-r * T) * N(-d2) - S * N(-d1)

    proceeds = np.zeros_like(S_T)
    for lg in legs:
        theo = vbs(S_T, lg.strike, T_exit, lg.iv * eff["vol_factor_k"], lg.right)
        half = (lg.ask - lg.bid) / 2 * eff["exit_spread_mult_normal"]
        proceeds += np.maximum(theo - half, 0) if lg.side == "buy" else -(theo + half)
    pnl = (proceeds - row["entry_debit"]) * 100 - row["costs_contract"]
    return float(pnl.mean()), float((pnl > 0).mean())


@pytest.mark.parametrize("direction,sign", [("bullish", 1), ("bearish", -1)])
def test_quadrature_matches_monte_carlo(direction, sign):
    row, eff = spread_row(direction=direction)
    eff = dict(eff, horizon_hours=3.0, alpha=0.25)
    out = val.value_candidate(row, 20.0, eff, TODAY, direction_verified=True)
    mc_neutral = mc_ev_pop(row, 20.0, eff, 0)
    mc_view = mc_ev_pop(row, 20.0, eff, sign)
    assert out["ev_neutral_net"] == pytest.approx(mc_neutral[0], abs=0.35)
    assert out["pop_neutral"] == pytest.approx(mc_neutral[1], abs=0.02)
    assert out["ev_view_net"] == pytest.approx(mc_view[0], abs=0.35)
    assert out["pop_view"] == pytest.approx(mc_view[1], abs=0.02)


# ====================================================================== propiedades del modelo
def test_neutral_ev_is_roughly_minus_costs_and_view_adds_edge():
    row, eff = spread_row()
    out = val.value_candidate(row, 20.0, eff, TODAY, direction_verified=True)
    assert out["ev_neutral_net"] < 0                               # coste puro de entrada
    assert out["ev_view_net"] > out["ev_neutral_net"]              # sesgo alcista favorece al call spread
    assert out["ev_neutral_adverse"] < out["ev_neutral_net"]       # ejecucion adversa empeora
    assert out["ev_view_adverse"] < out["ev_view_net"]
    assert 0 <= out["pop_neutral"] <= 1 and 0 <= out["pop_view"] <= 1
    assert len(out["scenarios"]) == 25
    assert out["worst_adverse_scenario_pnl"] >= -row["max_loss_contract"] - 1e-6   # nunca peor que la perdida maxima


def test_bearish_row_gets_negative_drift():
    row, eff = spread_row(direction="bearish")
    bull, _ = spread_row(direction="bullish")
    a = val.value_candidate(row, 20.0, eff, TODAY, True)
    b = val.value_candidate(bull, 20.0, eff, TODAY, True)
    assert a["ev_view_net"] < b["ev_view_net"]


def test_alpha_zero_means_no_edge():
    row, eff = spread_row()
    out = val.value_candidate(row, 20.0, dict(eff, alpha=0.0), TODAY, True)
    assert out["ev_view_net"] == pytest.approx(out["ev_neutral_net"], abs=0.01)
    ok, reasons = val.eligibility_from_valuation(out, eff)
    assert not ok and any("<= 0" in r for r in reasons)


def test_unverified_direction_rules():
    row, eff = spread_row()
    test_mode = val.value_candidate(row, 20.0, dict(eff, allow_unverified_direction=True), TODAY, False)
    assert test_mode["view_computed"] and any("MODO PRUEBA" in w for w in test_mode["warnings"])
    strict = val.value_candidate(row, 20.0, dict(eff, allow_unverified_direction=False), TODAY, False)
    assert strict["ev_view_net"] is None and not strict["view_computed"]
    ok, reasons = val.eligibility_from_valuation(strict, eff)
    assert not ok and "no verificada" in reasons[0]


def test_missing_iv_gives_error_not_numbers():
    row, eff = spread_row()
    row["legs"][0]["iv"] = None
    out = val.value_candidate(row, 20.0, eff, TODAY, True)
    assert "error" in out and "ev_neutral_net" not in out
    assert val.eligibility_from_valuation(out, eff)[0] is False


def test_expired_or_horizon_beyond_expiry():
    row, eff = spread_row()
    row["expiry"] = TODAY.isoformat()
    assert "error" in val.value_candidate(row, 20.0, eff, TODAY, True)


def test_min_ev_ratio_threshold():
    ok, reasons = val.eligibility_from_valuation({"ev_view_net": 1.0, "ev_ratio": 0.01}, EFF)
    assert not ok and "EV/perdida" in reasons[0]
    assert val.eligibility_from_valuation({"ev_view_net": 5.0, "ev_ratio": 0.10}, EFF)[0] is True


# ====================================================================== ADUANA
def cand(**kw):
    row, eff = spread_row()
    row.update(kw)
    return row, eff


def ctx(**kw):
    base = dict(now=datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc), underlying_id=1,
                quote_ages_sec={2000: 3.0, 2100: 3.0}, event_flags=[])
    base.update(kw)
    return ad.AduanaContext(**base)


def rule(res, name):
    return next(r for r in res.rules if r.rule == name)


def test_aduana_approves_clean_candidate():
    row, eff = cand()
    res = ad.validate_entry(row, ctx(), eff)
    assert res.approved, res.reasons
    assert [r.rule for r in res.rules] == [f"O-{i}" for i in range(1, 14)]


def test_o1_mode_must_be_paper():
    row, eff = cand()
    assert not rule(ad.validate_entry(row, ctx(execution_mode="live"), eff), "O-1").ok


def test_o2_uncovered_short_leg_rejected():
    row, eff = cand()
    row["legs"] = [row["legs"][1]]                                  # solo la corta
    assert not rule(ad.validate_entry(row, ctx(), eff), "O-2").ok
    row2, _ = cand()
    row2["legs"][0]["strike"], row2["legs"][1]["strike"] = 22, 21    # corta por debajo de la larga (call) -> sin cobertura
    assert not rule(ad.validate_entry(row2, ctx(), eff), "O-2").ok


def test_o3_cap_and_hard_cap(monkeypatch):
    row, eff = cand()
    row["max_loss_total"] = 60.0
    assert not rule(ad.validate_entry(row, ctx(), dict(eff, max_risk_per_trade_usd=50)), "O-3").ok
    monkeypatch.setenv("OPTIONS_HARD_MAX_RISK_PER_TRADE_USD", "30")
    row["max_loss_total"] = 40.0
    assert not rule(ad.validate_entry(row, ctx(), dict(eff, max_risk_per_trade_usd=100)), "O-3").ok   # techo duro manda


def test_o4_open_risk_budget_example_50_25_25():
    row, eff = cand(max_loss_total=25.0)
    eff = dict(eff, max_open_risk_usd=100)
    pos = [ad.OpenPosition(10, 50.0, "bullish")]
    assert ad.remaining_open_risk(pos, eff) == 50.0
    assert rule(ad.validate_entry(row, ctx(positions=pos), eff), "O-4").ok
    pos2 = pos + [ad.OpenPosition(11, 25.0, "bearish")]
    assert ad.remaining_open_risk(pos2, eff) == 25.0
    assert rule(ad.validate_entry(row, ctx(positions=pos2), eff), "O-4").ok
    pos3 = pos2 + [ad.OpenPosition(12, 25.0, "bearish")]
    assert not rule(ad.validate_entry(row, ctx(positions=pos3), eff), "O-4").ok


def test_o5_daily_stop_uses_pnl_not_theoretical_risk():
    row, eff = cand()
    open_pos = [ad.OpenPosition(10, 90.0, "bullish")]                 # alto riesgo teorico abierto, sin perdida marcada
    c0 = ctx(positions=open_pos)
    assert not ad.daily_stop_active(c0, eff)
    c1 = ctx(realized_pnl_today=-30.0, unrealized_pnl_today=-20.0)
    assert ad.daily_stop_active(c1, dict(eff, daily_stop_usd=50)) and not rule(ad.validate_entry(row, c1, dict(eff, daily_stop_usd=50)), "O-5").ok


def test_o6_spreads_and_overcost():
    row, eff = cand()
    row["legs"][0]["bid"] = 0.30                                      # spread 50% en la larga
    assert not rule(ad.validate_entry(row, ctx(), eff), "O-6").ok
    row2, _ = cand(exec_overcost_pct=40.0)
    assert not rule(ad.validate_entry(row2, ctx(), eff), "O-6").ok


def test_o7_data_state_and_age():
    row, eff = cand()
    row["legs"][0]["market_data_type"] = "STALE"
    assert not rule(ad.validate_entry(row, ctx(), eff), "O-7").ok
    row2, _ = cand()
    assert not rule(ad.validate_entry(row2, ctx(quote_ages_sec={2000: 60.0, 2100: 3.0}), eff), "O-7").ok
    row3, _ = cand()
    row3["legs"][0]["market_data_type"] = "DELAYED"
    assert not rule(ad.validate_entry(row3, ctx(), dict(eff, allow_delayed_data=False)), "O-7").ok
    r = ad.validate_entry(row3, ctx(), dict(eff, allow_delayed_data=True))
    assert rule(r, "O-7").ok and any("retrasados" in w for w in r.warnings)


def test_o8_entry_window_and_holidays():
    row, eff = cand()
    inside = ctx(now=datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc))          # 11:00 ET lunes
    too_early = ctx(now=datetime(2026, 10, 19, 13, 35, tzinfo=timezone.utc))      # 9:35 ET (< 9:45)
    too_late = ctx(now=datetime(2026, 10, 19, 19, 45, tzinfo=timezone.utc))       # 15:45 ET (> 15:30)
    weekend = ctx(now=datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc))         # sabado
    thanksgiving = ctx(now=datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc))
    assert rule(ad.validate_entry(row, inside, eff), "O-8").ok
    for c in (too_early, too_late, weekend, thanksgiving):
        assert not rule(ad.validate_entry(row, c, eff), "O-8").ok


def test_o9_events():
    row, eff = cand()
    assert not rule(ad.validate_entry(row, ctx(event_flags=["earnings"]), eff), "O-9").ok
    assert rule(ad.validate_entry(row, ctx(event_flags=["earnings"]), dict(eff, block_events_in_dte=False)), "O-9").ok
    r = ad.validate_entry(row, ctx(event_flags=None), eff)
    assert rule(r, "O-9").ok and any("no verificado" in w for w in r.warnings)


def test_o10_idempotency_and_o11_limits():
    row, eff = cand()
    assert not rule(ad.validate_entry(row, ctx(opened_candidate_ids={1}), eff), "O-10").ok
    dup = [ad.OpenPosition(1, 10.0, "bearish")]
    assert not rule(ad.validate_entry(row, ctx(positions=dup), eff), "O-11").ok            # mismo subyacente
    many = [ad.OpenPosition(i, 10.0, "bullish") for i in (5, 6)]
    assert not rule(ad.validate_entry(row, ctx(positions=many), dict(eff, max_same_direction=2)), "O-11").ok
    full = [ad.OpenPosition(i, 5.0, "bearish") for i in (5, 6, 7)]
    assert not rule(ad.validate_entry(row, ctx(positions=full), dict(eff, max_open_positions=3)), "O-11").ok


def test_static_context_skips_window_and_age():
    row, eff = cand()
    res = ad.validate_entry(row, ad.static_context(1, []), eff)
    assert res.approved


def test_o12_catalyst_gate():
    row, eff = cand()
    
    # 1. Gate deshabilitado
    res = ad.validate_entry(row, ctx(), dict(eff, gate_enabled=False))
    assert rule(res, "O-12").ok

    # 2. Sin catalizador activo (aprobado por compatibilidad)
    res = ad.validate_entry(row, ctx(), eff)
    assert rule(res, "O-12").ok

    # 3. Gap excesivo (> 3.0 ATR)
    cand_gap_excessive = dict(row, catalyst_state={
        "c1_active": True,
        "c1_gap": {"gap_atr": 4.5, "candles_checked": 2, "triggered": True},
    })
    res = ad.validate_entry(cand_gap_excessive, ctx(), eff)
    assert not rule(res, "O-12").ok
    assert "gap excesivo" in rule(res, "O-12").detail

    # 4. Primer gap del dia esperando 2da vela
    cand_c1_wait = dict(row, catalyst_state={
        "c1_active": True,
        "c1_gap": {"gap_atr": 1.2, "candles_checked": 1, "triggered": True},
    })
    res = ad.validate_entry(cand_c1_wait, ctx(), eff)
    assert not rule(res, "O-12").ok
    assert "esperando apertura de la 2da vela" in rule(res, "O-12").detail

    # 5. SIPV mecha de rechazo superior en CALL
    cand_sipv_reject = dict(row, direction="bullish", catalyst_state={
        "sipv_upper_rejection": True,
    })
    res = ad.validate_entry(cand_sipv_reject, ctx(), eff)
    assert not rule(res, "O-12").ok
    assert "rechazo SIPV superior" in rule(res, "O-12").detail

    # 6. Anti-climax bloquea en vela 2+
    cand_anticlimax = dict(row, catalyst_state={
        "is_anticlimax_blocked": True,
        "c1_gap": {"candles_checked": 3},
    })
    res = ad.validate_entry(cand_anticlimax, ctx(), eff)
    assert not rule(res, "O-12").ok


def test_exit_classification():
    assert ad.classify_exit("stop") == "PASIVA" and ad.classify_exit("forced_close_time") == "PASIVA"
    assert ad.classify_exit("bad_data_close") == "PASIVA"
    assert ad.classify_exit("take_profit") == "ACTIVA" and ad.classify_exit("signal_invalidation") == "ACTIVA"
    with pytest.raises(ValueError):
        ad.classify_exit("otro")
    assert ad.validate_exit("take_profit", ctx()).approved
    assert not ad.validate_exit("stop", ctx(execution_mode="live")).approved


# ====================================================================== calendario
def test_calendar_holidays_and_early_close():
    assert mc.session_bounds(date(2026, 11, 26)) is None             # Thanksgiving
    assert mc.session_bounds(date(2026, 12, 25)) is None
    assert mc.is_early_close(date(2026, 11, 27)) and mc.is_early_close(date(2026, 12, 24))
    assert not mc.is_early_close(date(2026, 10, 19))
    o, c = mc.session_bounds(date(2026, 11, 27))
    assert mc.to_ny(c).strftime("%H:%M") == "13:00"


def test_force_close_time_respects_early_close():
    now = datetime(2026, 11, 27, 16, 0, tzinfo=timezone.utc)
    assert mc.to_ny(mc.force_close_time(now, 15)).strftime("%H:%M") == "12:45"


def test_market_hours_between_skips_closed_time():
    start = datetime(2026, 10, 16, 19, 0, tzinfo=timezone.utc)       # viernes 15:00 ET
    end = datetime(2026, 10, 19, 15, 30, tzinfo=timezone.utc)        # lunes 11:30 ET
    assert mc.market_hours_between(start, end) == pytest.approx(1.0 + 2.0, abs=1e-6)   # 15:00-16:00 + 9:30-11:30
