"""Pruebas Sprint 2: opcionabilidad, estados de datos, seleccion de strikes, pacing, claim de jobs."""
from datetime import datetime, timedelta, timezone

import pytest

from app.options import settings_defaults as sd
from app.options.optionability import (
    OptionabilityInput, classify_quote, evaluate_optionability, expirations_in_window,
    select_strikes, strike_gap_pct,
)

EFF = sd.default_settings()
NOW = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)


def good(**kw):
    base = dict(symbol="AAA", price=20.0, has_options=True, expirations_in_window=2, strike_gap_pct=2.5,
                atm_oi=500, atm_volume=200, atm_spread_pct=5.0, event_in_dte=False, halted=False)
    base.update(kw)
    return OptionabilityInput(**base)


def test_optionable_ok():
    ok, reasons, _ = evaluate_optionability(good(), EFF)
    assert ok and reasons == []


@pytest.mark.parametrize("kw,frag", [
    (dict(has_options=False), "sin opciones"),
    (dict(price=3.0), "minimo"),
    (dict(atm_spread_pct=18.0), "spread ATM"),
    (dict(atm_oi=100), "open interest"),
    (dict(strike_gap_pct=9.0), "strikes"),
    (dict(expirations_in_window=0), "DTE"),
    (dict(event_in_dte=True), "evento"),
    (dict(halted=True), "halt"),
])
def test_rejections(kw, frag):
    ok, reasons, _ = evaluate_optionability(good(**kw), EFF)
    assert not ok and any(frag in r for r in reasons)


def test_missing_data_blocks_never_zero():
    ok, reasons, _ = evaluate_optionability(good(atm_oi=None, atm_spread_pct=None), EFF)
    assert not ok
    assert sum("dato no disponible" in r for r in reasons) == 2


def test_missing_price_blocks():
    ok, reasons, _ = evaluate_optionability(good(price=None), EFF)
    assert not ok


def test_unverified_event_is_warning_only():
    ok, _, warns = evaluate_optionability(good(event_in_dte=None), EFF)
    assert ok and any("no verificado" in w for w in warns)


def test_delayed_warning():
    _, _, warns = evaluate_optionability(good(data_states=["DELAYED"]), EFF)
    assert any("retrasados" in w for w in warns)


def q(**kw):
    base = dict(bid=1.0, ask=1.1, market_data_type="LIVE", received_at=NOW.isoformat())
    base.update(kw)
    return base


def test_quote_live_usable():
    assert classify_quote(q(), NOW, 15, True) == ("LIVE", True, None)


def test_quote_stale():
    old = (NOW - timedelta(seconds=60)).isoformat()
    state, usable, _ = classify_quote(q(received_at=old), NOW, 15, True)
    assert state == "STALE" and not usable


def test_quote_delayed_depends_on_flag():
    assert classify_quote(q(market_data_type="DELAYED"), NOW, 15, True)[1] is True
    assert classify_quote(q(market_data_type="DELAYED"), NOW, 15, False)[1] is False


def test_quote_frozen_unusable():
    assert classify_quote(q(market_data_type="FROZEN"), NOW, 15, True)[1] is False


def test_quote_crossed_or_missing():
    assert classify_quote(q(bid=1.2, ask=1.1), NOW, 15, True)[0] == "ERROR"
    assert classify_quote(q(bid=None), NOW, 15, True)[1] is False
    assert classify_quote(q(bid=0, ask=0), NOW, 15, True)[0] == "ERROR"


def test_quote_without_timestamp_unusable():
    assert classify_quote({"bid": 1, "ask": 1.1, "market_data_type": "LIVE"}, NOW, 15, True)[1] is False


def test_select_strikes_and_gap():
    strikes = [14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
    sel = select_strikes(strikes, 19.6, 3)
    assert sel == [17, 18, 19, 20, 21, 22]
    assert strike_gap_pct(strikes, 19.6) == pytest.approx(1 / 19.6 * 100, rel=0.01)
    assert strike_gap_pct([], 10) is None


def test_expirations_window():
    today = datetime(2026, 10, 19)
    exps = ["20261021", "20261030", "20261120", "20261230", "bad"]
    assert expirations_in_window(exps, today, 7, 30) == ["20261030"]
    assert expirations_in_window(exps, today, 7, 33) == ["20261030", "20261120"]


def test_rate_limiter_spaces_calls():
    from app.options.ib_client import RateLimiter
    t = {"now": 0.0}
    slept = []
    rl = RateLimiter(10, clock=lambda: t["now"], sleep=lambda d: (slept.append(d), t.__setitem__("now", t["now"] + d)))
    for _ in range(3):
        rl.wait()
    assert slept and sum(slept) == pytest.approx(0.2, abs=0.01)


class _Q:
    def __init__(self, store, name):
        self.s, self.n, self.f, self.upd = store, name, {}, None

    def select(self, *_): return self
    def eq(self, k, v): self.f[k] = v; return self
    def order(self, *_a, **_k): return self
    def limit(self, *_): return self
    def update(self, d): self.upd = d; return self

    def execute(self):
        rows = [r for r in self.s[self.n] if all(r.get(k) == v for k, v in self.f.items())]
        if self.upd is not None:
            for r in rows:
                r.update(self.upd)
        class R: pass
        r = R(); r.data = rows; return r


class _SB:
    def __init__(self, jobs): self.s = {"opt_jobs": jobs}
    def table(self, n): return _Q(self.s, n)


def test_claim_job_marks_running():
    from app.options.worker import _claim_job
    sb = _SB([{"id": 1, "status": "pending", "type": "scan", "created_at": "x"}])
    job = _claim_job(sb)
    assert job["id"] == 1 and sb.s["opt_jobs"][0]["status"] == "running"
    assert _claim_job(sb) is None
