"""Filtro de opcionabilidad (doc §7) y validez de cotizaciones (doc §14.3). Logica pura, sin IO."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class OptionabilityInput:
    symbol: str
    price: float | None = None
    has_options: bool | None = None
    expirations_in_window: int | None = None
    strike_gap_pct: float | None = None
    atm_oi: float | None = None
    atm_volume: float | None = None
    atm_spread_pct: float | None = None
    event_in_dte: bool | None = None      # None = no verificado
    halted: bool | None = None
    iv_hv_ratio: float | None = None
    data_states: list[str] = field(default_factory=list)


def evaluate_optionability(inp: OptionabilityInput, eff: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    """Devuelve (optionable, motivos_de_rechazo, advertencias). Dato ausente = rechazo, nunca cero."""
    reasons: list[str] = []
    warns: list[str] = []

    if inp.has_options is not True:
        return False, ["sin opciones listadas"], warns
    if inp.price is None:
        return False, ["precio del subyacente no disponible"], warns
    if inp.price < eff["min_underlying_price"]:
        reasons.append(f"precio {inp.price:.2f} < minimo {eff['min_underlying_price']}")
    if inp.halted:
        reasons.append("subyacente en halt")
    if not inp.expirations_in_window:
        reasons.append("sin vencimientos dentro de la ventana DTE")

    checks = (
        ("strike_gap_pct", inp.strike_gap_pct, lambda v: v <= eff["max_strike_gap_pct"],
         f"separacion de strikes > {eff['max_strike_gap_pct']}%"),
        ("atm_oi", inp.atm_oi, lambda v: v >= eff["min_atm_open_interest"],
         f"open interest ATM < {eff['min_atm_open_interest']}"),
        ("atm_spread_pct", inp.atm_spread_pct, lambda v: v <= eff["max_atm_spread_pct"],
         f"spread ATM > {eff['max_atm_spread_pct']}%"),
    )
    for name, val, ok, msg in checks:
        if val is None:
            reasons.append(f"dato no disponible: {name}")
        elif not ok(val):
            reasons.append(msg)

    if inp.atm_volume is None:
        warns.append("volumen ATM no disponible")
    elif inp.atm_volume < eff["pref_atm_volume"]:
        warns.append(f"volumen ATM bajo (< {eff['pref_atm_volume']})")

    if inp.event_in_dte is None:
        warns.append("earnings/catalizador no verificado")
    elif inp.event_in_dte and eff["block_events_in_dte"]:
        reasons.append("evento binario dentro del DTE")

    if inp.iv_hv_ratio is not None and inp.iv_hv_ratio > eff["iv_hv_expensive"]:
        warns.append("prima cara (IV/HV alto)")
    if "DELAYED" in inp.data_states:
        warns.append("datos retrasados (solo prueba)")

    return (not reasons), reasons, warns


def classify_quote(q: dict[str, Any], now: datetime | None, max_age_sec: float,
                   allow_delayed: bool) -> tuple[str, bool, str | None]:
    """Estado de datos de una cotizacion -> (estado, utilizable, motivo).

    Estados: LIVE, DELAYED, FROZEN, UNKNOWN, STALE, ERROR. La antiguedad se mide con received_at
    (en DELAYED el quote_time ya viene ~15 min atrasado por naturaleza).
    """
    now = now or datetime.now(timezone.utc)
    bid, ask = q.get("bid"), q.get("ask")
    base = q.get("market_data_type") or "UNKNOWN"

    if bid is None or ask is None:
        return ("ERROR" if q.get("errors") else base if base != "LIVE" else "UNKNOWN"), False, "sin bid/ask"
    if bid <= 0 or ask <= 0 or ask < bid:
        return "ERROR", False, "bid/ask invalido o cruzado"

    recv = q.get("received_at")
    if recv:
        try:
            r = datetime.fromisoformat(recv) if isinstance(recv, str) else recv
            if r.tzinfo is None:
                r = r.replace(tzinfo=timezone.utc)
            if (now - r).total_seconds() > max_age_sec:
                return "STALE", False, "cotizacion obsoleta"
        except ValueError:
            return "ERROR", False, "received_at invalido"
    else:
        return "UNKNOWN", False, "sin timestamp de recepcion"

    if base == "LIVE":
        return "LIVE", True, None
    if base == "DELAYED":
        return ("DELAYED", True, None) if allow_delayed else ("DELAYED", False, "datos retrasados no permitidos")
    if base == "FROZEN":
        return "FROZEN", False, "datos congelados"
    return "UNKNOWN", False, "tipo de dato desconocido"


def strike_gap_pct(strikes: list[float], price: float) -> float | None:
    """Separacion media entre los strikes mas cercanos al precio, en % del precio."""
    if not strikes or not price:
        return None
    near = sorted(sorted(strikes, key=lambda k: abs(k - price))[:5])
    if len(near) < 2:
        return None
    gaps = [b - a for a, b in zip(near, near[1:]) if b > a]
    return round(sum(gaps) / len(gaps) / price * 100, 3) if gaps else None


def select_strikes(strikes: list[float], price: float, n_each_side: int = 3) -> list[float]:
    """n strikes por debajo y por encima del precio (ATM incluido en el lado superior)."""
    below = sorted([k for k in strikes if k < price], reverse=True)[:n_each_side]
    above = sorted([k for k in strikes if k >= price])[:n_each_side]
    return sorted(below + above)


def expirations_in_window(expirations: list[str], today: datetime, dte_min: int, dte_max: int) -> list[str]:
    out = []
    for e in expirations:
        try:
            d = datetime.strptime(e, "%Y%m%d").date()
        except ValueError:
            continue
        dte = (d - today.date()).days
        if dte_min <= dte <= dte_max:
            out.append(e)
    return sorted(out)
