"""Pruebas del modulo Options - fundacion (Sprint 1)."""
import pathlib

import pytest

from app.options import readonly_adapter as ra
from app.options import settings_defaults as sd

OPTIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "options"
API_FILE = pathlib.Path(__file__).resolve().parents[1] / "api" / "options.py"


class FakeClient:
    def __init__(self):
        self.calls = []

    def reqMktData(self, *a):
        self.calls.append(("reqMktData", a))
        return 1

    def placeOrder(self, *a):  # existe en el cliente real; el adaptador NO debe permitirlo
        raise AssertionError("placeOrder no debe ejecutarse")


def test_adapter_allows_whitelist():
    c = FakeClient()
    ad = ra.OptionsReadOnlyAdapter(c)
    assert ad.call("reqMktData", 1, None) == 1
    assert c.calls


@pytest.mark.parametrize("name", ["placeOrder", "cancelOrder", "reqGlobalCancel", "exerciseOptions"])
def test_adapter_blocks_order_methods(name):
    ad = ra.OptionsReadOnlyAdapter(FakeClient())
    with pytest.raises(ra.ForbiddenBrokerCall):
        ad.call(name)
    with pytest.raises(ra.ForbiddenBrokerCall):
        getattr(ad, name)


def test_no_order_code_in_options_module():
    """El modulo no debe referenciar funciones de ordenes del broker."""
    files = list(OPTIONS_DIR.rglob("*.py")) + [API_FILE]
    offenders = []
    for f in files:
        if f.name == "readonly_adapter.py":
            continue  # define las listas negras como texto
        text = f.read_text(encoding="utf-8")
        for tok in ra.FORBIDDEN_TOKENS:
            if tok in text:
                offenders.append((f.name, tok))
    assert not offenders, offenders


def test_defaults_valid():
    d = sd.default_settings()
    assert sd.validate_cross_rules(d) == []
    clean, errors = sd.validate_settings(d)
    assert errors == []


def test_range_and_unknown_rejected():
    _, errors = sd.validate_settings({"alpha": 5, "nope": 1, "max_risk_per_trade_usd": -1})
    assert len(errors) == 3


def test_weights_must_sum_100():
    d = sd.default_settings()
    d["w_expectancy"] = 40
    assert any("pesos" in e for e in sd.validate_cross_rules(d))


def test_dte_order():
    d = sd.default_settings()
    d["dte_min"] = 30
    assert any("dte_min" in e for e in sd.validate_cross_rules(d))


def test_hard_cap_clips_effective(monkeypatch):
    monkeypatch.setenv("OPTIONS_HARD_MAX_RISK_PER_TRADE_USD", "50")
    eff = sd.effective_settings({"max_risk_per_trade_usd": 100})
    assert eff["max_risk_per_trade_usd"] == 50


def test_execution_mode_only_paper(monkeypatch):
    monkeypatch.setenv("OPTIONS_EXECUTION_MODE", "live")
    assert sd.execution_mode_ok() is False
    monkeypatch.setenv("OPTIONS_EXECUTION_MODE", "paper")
    assert sd.execution_mode_ok() is True


def test_data_state_mapping():
    assert ra.market_data_type_to_state(1) == "LIVE"
    assert ra.market_data_type_to_state(3) == "DELAYED"
    assert ra.market_data_type_to_state(None) == "UNKNOWN"


def test_delayed_allowed_by_default_for_test_phase():
    d = sd.default_settings()
    assert d['allow_delayed_data'] is True
    clean, errors = sd.validate_settings({'allow_delayed_data': False})
    assert errors == [] and clean['allow_delayed_data'] is False
