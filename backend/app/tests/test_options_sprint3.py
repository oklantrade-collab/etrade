"""Pruebas Sprint 3: estrategias V1, payoff, sizing, rechazos, datos faltantes."""
from datetime import date

import pytest

from app.options import bs
from app.options import settings_defaults as sd
from app.options import strategies as st

EFF = sd.default_settings()
EFF.update(commission_per_contract=0.65, extra_fees_per_contract=0.05, slippage_normal=0.01,
           min_contract_oi=100, min_contract_volume=10)
TODAY = date(2026, 10, 19)
EXP = date(2026, 11, 6)  # 18 DTE


def mk(right, strike, bid, ask, delta=None, iv=0.5, oi=500, vol=100, usable=True, cid=None):
    return st.Q(contract_id=cid or int(strike * 10), conid=int(strike * 100) + (1 if right == "P" else 0), right=right,
                strike=strike, expiry=EXP, bid=bid, ask=ask, volume=vol, open_interest=oi, iv=iv, delta=delta,
                usable=usable, market_data_type="LIVE")


# ---------- costes
def test_costs_per_contract():
    # 1 pierna: 2*(0.65+0.05) + 0.01*100 = 2.40 ; 2 piernas: 4.80
    assert st.contract_costs(1, EFF) == pytest.approx(2.40)
    assert st.contract_costs(2, EFF) == pytest.approx(4.80)


# ---------- long call
def test_long_call_metrics():
    q = mk("C", 20, 0.28, 0.30, delta=0.45)
    c, why = st.build_long("long_call", q, 19.8, TODAY, EFF)
    assert c and not why
    assert c.entry_debit == 0.30
    assert c.max_loss_contract == pytest.approx(30 + 2.40)           # 32.40
    assert c.qty == 1                                                # floor(50/32.4)
    assert c.max_loss_total == pytest.approx(32.40)
    assert c.max_profit_contract is None
    assert c.breakeven == pytest.approx(20 + 0.324)
    assert st.pnl_at_expiry(c, 10) == pytest.approx(-c.max_loss_contract)   # pierde todo
    assert st.pnl_at_expiry(c, c.breakeven) == pytest.approx(0, abs=0.01)
    assert st.pnl_at_expiry(c, 22) == pytest.approx((2 - 0.30) * 100 - 2.40)


def test_long_put_breakeven_and_payoff():
    q = mk("P", 20, 0.28, 0.30, delta=-0.45)
    c, _ = st.build_long("long_put", q, 20.2, TODAY, EFF)
    assert c.breakeven == pytest.approx(20 - 0.324)
    assert st.pnl_at_expiry(c, 30) == pytest.approx(-c.max_loss_contract)
    assert st.pnl_at_expiry(c, c.breakeven) == pytest.approx(0, abs=0.01)


def test_long_rejected_when_exceeds_risk():
    q = mk("C", 20, 0.55, 0.60, delta=0.45)            # 60 + 2.4 = 62.4 > 50
    c, why = st.build_long("long_call", q, 19.8, TODAY, EFF)
    assert c is None and "riesgo por operacion" in why[0]


def test_qty_scales_with_risk():
    eff = dict(EFF, max_risk_per_trade_usd=100)
    q = mk("C", 20, 0.18, 0.20, delta=0.45)            # 20 + 2.4 = 22.4 -> qty 4
    c, _ = st.build_long("long_call", q, 19.8, TODAY, eff)
    assert c.qty == 4


# ---------- datos faltantes / calidad
def test_missing_delta_and_iv_rejected():
    q = mk("C", 20, 0.28, 0.30, delta=None, iv=None)
    c, why = st.build_long("long_call", q, 19.8, TODAY, EFF)
    assert c is None and any("delta" in w for w in why)


def test_delta_falls_back_to_bs_from_iv():
    q = mk("C", 20, 0.28, 0.30, delta=None, iv=0.5)
    c, _ = st.build_long("long_call", q, 20.0, TODAY, EFF)
    assert c and c.delta_source == "bs_from_iv" and c.warnings


def test_delta_out_of_range_rejected():
    q = mk("C", 25, 0.05, 0.06, delta=0.08)
    c, why = st.build_long("long_call", q, 20.0, TODAY, EFF)
    assert c is None and any("fuera de" in w for w in why)


def test_unusable_and_missing_oi_volume():
    c, why = st.build_long("long_call", mk("C", 20, .28, .30, delta=.45, usable=False), 19.8, TODAY, EFF)
    assert c is None and "no utilizable" in why[0]
    c, why = st.build_long("long_call", mk("C", 20, .28, .30, delta=.45, oi=None, vol=None), 19.8, TODAY, EFF)
    assert c is None and sum("no disponible" in w for w in why) == 2


def test_wide_leg_spread_rejected():
    c, why = st.build_long("long_call", mk("C", 20, 0.20, 0.30, delta=.45), 19.8, TODAY, EFF)  # 33%
    assert c is None and any("spread de pierna" in w for w in why)


# ---------- spreads
def test_bull_call_spread_metrics():
    lo = mk("C", 20, 0.58, 0.60, delta=0.50)
    hi = mk("C", 21, 0.28, 0.30, delta=0.30)
    c, why = st.build_spread("bull_call_spread", lo, hi, 20.0, TODAY, dict(EFF, max_exec_overcost_pct=25))
    assert c, why
    assert c.entry_debit == pytest.approx(0.32)                    # ask largo 0.60 - bid corto 0.28
    assert c.mid_debit == pytest.approx(0.30)                      # 0.59 - 0.29
    assert c.max_loss_contract == pytest.approx(32 + 4.80)
    assert c.max_profit_contract == pytest.approx((1 - 0.32) * 100 - 4.80)
    assert c.breakeven == pytest.approx(20 + 0.368)
    assert st.pnl_at_expiry(c, 15) == pytest.approx(-c.max_loss_contract)
    assert st.pnl_at_expiry(c, 30) == pytest.approx(c.max_profit_contract)
    assert st.pnl_at_expiry(c, c.breakeven) == pytest.approx(0, abs=0.01)


def test_bear_put_spread_metrics():
    hi = mk("P", 21, 0.58, 0.60, delta=-0.50)
    lo = mk("P", 20, 0.28, 0.30, delta=-0.30)
    c, why = st.build_spread("bear_put_spread", hi, lo, 21.0, TODAY, dict(EFF, max_exec_overcost_pct=25))
    assert c, why
    assert c.breakeven == pytest.approx(21 - 0.368)
    assert st.pnl_at_expiry(c, 30) == pytest.approx(-c.max_loss_contract)
    assert st.pnl_at_expiry(c, 10) == pytest.approx(c.max_profit_contract)


def test_malformed_spreads_rejected():
    lo, hi = mk("C", 20, .58, .60, delta=.5), mk("C", 21, .28, .30, delta=.3)
    c, why = st.build_spread("bull_call_spread", hi, lo, 20.0, TODAY, EFF)   # invertido
    assert c is None and "mal construido" in why[0]
    p_hi, p_lo = mk("P", 21, .58, .60, delta=-.5), mk("P", 20, .28, .30, delta=-.3)
    c, why = st.build_spread("bear_put_spread", p_lo, p_hi, 21.0, TODAY, EFF)
    assert c is None and "mal construido" in why[0]
    other = st.Q(**{**lo.__dict__, "expiry": date(2026, 11, 13)})
    c, why = st.build_spread("bull_call_spread", other, hi, 20.0, TODAY, EFF)
    assert c is None and "distinto vencimiento" in why[0]


def test_spread_width_limits():
    lo, hi = mk("C", 20, .58, .60, delta=.5), mk("C", 27, .01, .05, delta=.05)
    c, why = st.build_spread("bull_call_spread", lo, hi, 20.0, TODAY, EFF)
    assert c is None and "ancho" in why[0]


def test_spread_debit_not_below_width_or_positive():
    lo, hi = mk("C", 20, 1.10, 1.12, delta=.5), mk("C", 21, .10, .11, delta=.1)
    c, why = st.build_spread("bull_call_spread", lo, hi, 20.0, TODAY, EFF)   # debito 1.02 >= ancho 1
    assert c is None and "sin beneficio posible" in why[0]
    lo2, hi2 = mk("C", 20, .28, .30, delta=.5), mk("C", 21, .38, .40, delta=.3)
    c, why = st.build_spread("bull_call_spread", lo2, hi2, 20.0, TODAY, EFF)  # debito negativo
    assert c is None and "<= 0" in why[0]


def test_spread_exec_overcost_limit():
    lo = mk("C", 20, 0.50, 0.60, delta=0.5)        # mid .55
    hi = mk("C", 21, 0.20, 0.30, delta=0.3)        # mid .25  -> debit mid .30, exec .40 (+33%)
    c, why = st.build_spread("bull_call_spread", lo, hi, 20.0, TODAY, dict(EFF, max_leg_spread_pct=40, max_exec_overcost_pct=10))
    assert c is None and "sobrecoste" in why[0]


def test_leg_missing_quote_rejected_in_spread():
    lo = mk("C", 20, .58, .60, delta=.5)
    hi = mk("C", 21, None, None, delta=.3)
    c, why = st.build_spread("bull_call_spread", lo, hi, 20.0, TODAY, EFF)
    assert c is None and any("pierna corta" in w for w in why)


# ---------- generador
def test_generate_respects_flags_and_direction():
    qs = [mk("C", 19, 1.0, 1.05, .6), mk("C", 20, .58, .60, .5), mk("C", 21, .28, .30, .3),
          mk("P", 19, .28, .30, -.3), mk("P", 20, .58, .60, -.5), mk("P", 21, 1.0, 1.05, -.6)]
    eff = dict(EFF, max_risk_per_trade_usd=100, max_exec_overcost_pct=25)
    valid, rej = st.generate(qs, 20.0, TODAY, eff)
    kinds = {c.strategy for c in valid}
    assert "bull_call_spread" in kinds and "bear_put_spread" in kinds
    assert all(c.max_loss_total <= 100 for c in valid)
    only_bull, _ = st.generate(qs, 20.0, TODAY, eff, directions=("bullish",))
    assert all(c.direction == "bullish" for c in only_bull)
    off, _ = st.generate(qs, 20.0, TODAY, dict(eff, strat_long_call=False, strat_bull_call_spread=False), ("bullish",))
    assert off == []


def test_generate_no_forced_candidates_when_nothing_fits():
    qs = [mk("C", 20, 2.0, 2.1, .5), mk("C", 21, 1.2, 1.3, .3)]
    valid, rej = st.generate(qs, 20.0, TODAY, EFF, ("bullish",))
    assert valid == [] and rej


def test_exit_plan_values():
    c, _ = st.build_long("long_call", mk("C", 20, .28, .30, delta=.45), 19.8, TODAY, EFF)
    assert c.exit_plan["take_profit_premium"] == pytest.approx(0.30 * 1.75)
    assert c.exit_plan["stop_premium"] == pytest.approx(0.30 * 0.5)


# ---------- BS y persistencia
def test_bs_put_call_parity_and_delta():
    S, K, T, r, s = 100, 100, 0.25, 0.04, 0.3
    c, p = bs.bs_price(S, K, T, r, s, "C"), bs.bs_price(S, K, T, r, s, "P")
    import math
    assert c - p == pytest.approx(S - K * math.exp(-r * T), abs=1e-6)
    assert 0.5 < bs.bs_delta(S, K, T, r, s, "C") < 0.6
    assert bs.bs_delta(S, K, 0, r, s, "C") is None and bs.bs_price(S, K, T, r, None, "C") is None


def test_payoff_curve_from_row():
    from app.options.candidates import payoff_curve
    row = {"legs": [{"side": "buy", "right": "C", "strike": 20}, {"side": "sell", "right": "C", "strike": 21}],
           "entry_debit": 0.30, "costs_contract": 4.8}
    pts = payoff_curve(row)
    assert pts and min(p["pnl"] for p in pts) == pytest.approx(-34.8) and max(p["pnl"] for p in pts) == pytest.approx(65.2)
    assert payoff_curve({"legs": [], "entry_debit": None}) == []


def test_candidate_row_has_null_for_pending_valuation():
    from app.options.candidates import candidate_row
    c, _ = st.build_long("long_call", mk("C", 20, .28, .30, delta=.45), 19.8, TODAY, EFF)
    row = candidate_row(c, 1, "unverified", 3, {}, "2026-10-19T00:00:00+00:00")
    assert "ev_view_net" not in row and "score" not in row      # quedan NULL en BD, nunca 0
    assert row["eligibility_status"] == "pending" and row["direction_source"] == "unverified"

