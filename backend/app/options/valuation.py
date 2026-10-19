"""Valoracion y simulacion (doc §10). Logica pura.

Modelo:
- sigma_h = IV * k * sqrt(h / (252 * 6.5))            (h = horas de mercado hasta la salida simulada)
- Distribucion lognormal del precio de salida con log-retorno ~ N(-0.5*sigma_h^2 + mu, sigma_h):
    A (neutral): mu = 0                      -> E[S_T] = S0. Su expectativa es ~ -costes (coste puro de entrada).
    B (sesgo APEX): mu = direccion * alpha * sigma_h   (alpha = hipotesis a calibrar, NO un hecho)
- Repricing al momento de salida con Black-Scholes (IV por pierna, tiempo restante) y escenarios de IV.
- Salida: se vende al bid / se recompra al ask: mitad del spread de entrada x multiplicador (normal 1.0, adverso 1.5).
- Americanas: se ignora el ejercicio anticipado (horizonte intradiario) -> limitacion documentada.
- Integracion numerica por cuadratura sobre z ~ N(0,1) (201 puntos, +-6 sigma). Un contraste Monte Carlo
  independiente vive en los tests (Gate G2).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.options import bs

TRADING_YEAR_HOURS = 252 * 6.5
Z_MAX, N_POINTS = 6.0, 201


def _grid() -> list[tuple[float, float]]:
    """(z, peso) con peso = pdf normal * dz, normalizados a 1."""
    dz = 2 * Z_MAX / (N_POINTS - 1)
    zs = [-Z_MAX + i * dz for i in range(N_POINTS)]
    ws = [math.exp(-0.5 * z * z) for z in zs]
    tot = sum(ws)
    return [(z, w / tot) for z, w in zip(zs, ws)]


_GRID = _grid()


def sigma_h(iv: float, k: float, h_hours: float) -> float:
    return iv * k * math.sqrt(h_hours / TRADING_YEAR_HOURS)


@dataclass
class LegV:
    side: str            # 'buy' | 'sell'
    right: str
    strike: float
    iv: float            # IV del broker (decimal, ej. 0.45)
    bid: float
    ask: float


def legs_from_row(legs: list[dict[str, Any]]) -> list[LegV] | None:
    out = []
    for l in legs:
        if any(l.get(k) is None for k in ("iv", "bid", "ask", "strike")) or not l.get("iv"):
            return None
        out.append(LegV(l["side"], l["right"], float(l["strike"]), float(l["iv"]), float(l["bid"]), float(l["ask"])))
    return out


def pnl_after(legs: list[LegV], entry_debit: float, costs_contract: float, S_T: float, T_exit: float, r: float,
              iv_shift: float, k: float, exit_mult: float, extra_slip_usd: float = 0.0) -> float | None:
    """P&L neto por contrato si al cierre simulado el subyacente vale S_T. None si no se puede valorar."""
    proceeds = 0.0
    for lg in legs:
        theo = bs.bs_price(S_T, lg.strike, T_exit, r, lg.iv * k * (1.0 + iv_shift), lg.right)
        if theo is None:
            return None
        half = (lg.ask - lg.bid) / 2.0 * exit_mult
        if lg.side == "buy":      # vendemos la pierna larga al bid
            proceeds += max(theo - half, 0.0)
        else:                     # recompramos la corta al ask
            proceeds -= theo + half
    return (proceeds - entry_debit) * 100.0 - costs_contract - extra_slip_usd


def _expect(legs, entry_debit, costs, S0, sig_h, mu, T_exit, r, iv_shift, k, exit_mult, extra_slip):
    ev = pop = mean_s = 0.0
    for z, w in _GRID:
        S_T = S0 * math.exp(-0.5 * sig_h ** 2 + mu + sig_h * z)
        p = pnl_after(legs, entry_debit, costs, S_T, T_exit, r, iv_shift, k, exit_mult, extra_slip)
        if p is None:
            return None
        ev += w * p
        pop += w * (1.0 if p > 0 else 0.0)
        mean_s += w * S_T
    return {"ev": ev, "pop": pop, "mean_exit_price": mean_s}


def value_candidate(row: dict[str, Any], S0: float, eff: dict[str, Any], today: date,
                    direction_verified: bool) -> dict[str, Any]:
    """Valora una candidata (fila de opt_candidates). Devuelve metricas o {'error': motivo}. Nunca rellena con ceros."""
    legs = legs_from_row(row.get("legs") or [])
    if not legs:
        return {"error": "IV/bid/ask de alguna pierna no disponible: valoracion imposible"}
    if row.get("entry_debit") is None or row.get("costs_contract") is None:
        return {"error": "debito o costes no disponibles"}
    expiry = date.fromisoformat(row["expiry"]) if isinstance(row["expiry"], str) else row["expiry"]
    T0 = (expiry - today).days / 365.0
    if T0 <= 0:
        return {"error": "vencimiento no futuro"}
    h = float(eff["horizon_hours"])
    k = float(eff["vol_factor_k"])
    r = float(eff["risk_free_rate_pct"]) / 100.0
    T_exit = T0 - h / TRADING_YEAR_HOURS
    if T_exit <= 0:
        return {"error": "horizonte supera el vencimiento"}
    # IV de referencia = IV de la pierna larga (la mas cercana al dinero por el rango de delta)
    iv_ref = next((lg.iv for lg in legs if lg.side == "buy"), legs[0].iv)
    sig = sigma_h(iv_ref, k, h)
    move_expected = S0 * sig
    entry, costs = float(row["entry_debit"]), float(row["costs_contract"])
    n_legs = len(legs)
    extra_adv = max(float(eff["slippage_adverse"]) - float(eff["slippage_normal"]), 0.0) * 100.0 * n_legs
    m_norm, m_adv = float(eff["exit_spread_mult_normal"]), float(eff["exit_spread_mult_adverse"])

    sign = 1.0 if row["direction"] == "bullish" else -1.0
    mu_view = sign * float(eff["alpha"]) * sig
    warnings: list[str] = []
    view_ok = direction_verified or bool(eff.get("allow_unverified_direction"))
    if not direction_verified:
        warnings.append("direccion APEX no verificada" + (": EV con sesgo calculado en MODO PRUEBA" if view_ok else ": EV con sesgo NO calculado"))

    A = _expect(legs, entry, costs, S0, sig, 0.0, T_exit, r, 0.0, k, m_norm, 0.0)
    A_adv = _expect(legs, entry, costs, S0, sig, 0.0, T_exit, r, 0.0, k, m_adv, extra_adv)
    if A is None or A_adv is None:
        return {"error": "no se pudo revalorar alguna pierna (IV/tiempo invalidos)"}
    B = B_adv = None
    ev_reduced_bias = None
    ev_iv_minus_10 = None
    ev_vol_k08 = None
    ev_vol_k12 = None
    if view_ok:
        B = _expect(legs, entry, costs, S0, sig, mu_view, T_exit, r, 0.0, k, m_norm, 0.0)
        B_adv = _expect(legs, entry, costs, S0, sig, mu_view, T_exit, r, 0.0, k, m_adv, extra_adv)
        ev_reduced_bias = _expect(legs, entry, costs, S0, sig, 0.5 * mu_view, T_exit, r, 0.0, k, m_norm, 0.0)
        ev_iv_minus_10 = _expect(legs, entry, costs, S0, sig, mu_view, T_exit, r, -0.10, k, m_norm, 0.0)
        sig_08 = sigma_h(iv_ref, 0.8, h)
        sig_12 = sigma_h(iv_ref, 1.2, h)
        mu_08 = sign * float(eff["alpha"]) * sig_08
        mu_12 = sign * float(eff["alpha"]) * sig_12
        ev_vol_k08 = _expect(legs, entry, costs, S0, sig_08, mu_08, T_exit, r, 0.0, 0.8, m_norm, 0.0)
        ev_vol_k12 = _expect(legs, entry, costs, S0, sig_12, mu_12, T_exit, r, 0.0, 1.2, m_norm, 0.0)

    # Net Greeks per candidate (Doc §8.3)
    greeks_net = None
    delta_shares = 0.0
    gamma_tot = 0.0
    vega_tot = 0.0
    theta_tot = 0.0
    greeks_available = True
    for lg in legs:
        side_mult = 1.0 if lg.side == "buy" else -1.0
        d = bs.bs_delta(S0, lg.strike, T0, r, lg.iv, lg.right)
        g = bs.bs_gamma(S0, lg.strike, T0, r, lg.iv)
        v = bs.bs_vega(S0, lg.strike, T0, r, lg.iv)
        th = bs.bs_theta(S0, lg.strike, T0, r, lg.iv, lg.right)
        if any(x is None for x in (d, g, v, th)):
            greeks_available = False
            break
        delta_shares += side_mult * 100.0 * d
        gamma_tot += side_mult * 100.0 * g
        vega_tot += side_mult * 100.0 * v
        theta_tot += side_mult * 100.0 * th

    if greeks_available:
        greeks_net = {
            "source": "MODEL",
            "delta_shares": round(delta_shares, 2),
            "delta_usd": round(delta_shares * S0, 2),
            "gamma": round(gamma_tot, 4),
            "vega_point": round(vega_tot, 2),
            "theta_day": round(theta_tot, 2),
        }

    # Sensitivities grid (Doc §8.2)
    sensitivities = {
        "base": _r2(B["ev"]) if B else _r2(A["ev"]),
        "reduced_bias": _r2(ev_reduced_bias["ev"]) if ev_reduced_bias else None,
        "no_bias": _r2(A["ev"]),
        "adverse_exec": _r2(B_adv["ev"]) if B_adv else _r2(A_adv["ev"]),
        "iv_shock_minus_10": _r2(ev_iv_minus_10["ev"]) if ev_iv_minus_10 else None,
        "vol_k_0_8": _r2(ev_vol_k08["ev"]) if ev_vol_k08 else None,
        "vol_k_1_2": _r2(ev_vol_k12["ev"]) if ev_vol_k12 else None,
    }
    valid_sens_evs = [v for v in sensitivities.values() if v is not None]
    ev_min = min(valid_sens_evs) if valid_sens_evs else None
    ev_max = max(valid_sens_evs) if valid_sens_evs else None
    ev_range = round(ev_max - ev_min, 2) if (ev_max is not None and ev_min is not None) else None

    # ev_robust: True if EV remains > 0 in reduced bias, adverse execution, and IV -10% (§8.2)
    ev_robust = False
    if B and ev_reduced_bias and B_adv and ev_iv_minus_10:
        ev_robust = (
            ev_reduced_bias["ev"] > 0
            and B_adv["ev"] > 0
            and ev_iv_minus_10["ev"] > 0
        )

    # Escenarios determinista: movimiento del subyacente (en sigmas) x cambio relativo de IV (normal y adverso)
    scenarios = []
    for iv_shift in (-0.20, -0.10, 0.0, 0.10, 0.20):
        for zmove in (-2.0, -1.0, 0.0, 1.0, 2.0):
            S_T = S0 * math.exp(-0.5 * sig ** 2 + zmove * sig)
            scenarios.append({
                "iv_shift": iv_shift, "move_sigmas": zmove, "price": round(S_T, 4),
                "pnl_normal": _r2(pnl_after(legs, entry, costs, S_T, T_exit, r, iv_shift, k, m_norm)),
                "pnl_adverse": _r2(pnl_after(legs, entry, costs, S_T, T_exit, r, iv_shift, k, m_adv, extra_adv)),
            })
    worst_adverse = min((s["pnl_adverse"] for s in scenarios if s["pnl_adverse"] is not None), default=None)

    max_loss = float(row["max_loss_contract"])
    out = {
        "horizon_hours": h, "sigma_h": round(sig, 6), "expected_move": round(move_expected, 4),
        "iv_ref": iv_ref, "alpha_used": float(eff["alpha"]), "T0_years": round(T0, 6), "T_exit_years": round(T_exit, 6),
        "ev_neutral_net": round(A["ev"], 2), "pop_neutral": round(A["pop"], 4),
        "ev_neutral_adverse": round(A_adv["ev"], 2),
        "ev_view_net": _r2(B["ev"]) if B else None, "pop_view": round(B["pop"], 4) if B else None,
        "ev_view_adverse": _r2(B_adv["ev"]) if B_adv else None,
        "ev_ratio": round(B["ev"] / max_loss, 4) if B and max_loss > 0 else None,
        "worst_adverse_scenario_pnl": worst_adverse,
        "greeks_net": greeks_net,
        "sensitivities": sensitivities,
        "ev_robust": ev_robust,
        "ev_min": ev_min,
        "ev_range": ev_range,
        "scenarios": scenarios, "warnings": warnings, "view_computed": bool(B),
        "model": {"dist": "lognormal", "quadrature_points": N_POINTS, "pricing": "black-scholes",
                  "american_early_exercise": "ignored (limitacion V1)"},
    }
    return out


def _r2(v):
    return None if v is None else round(v, 2)


def eligibility_from_valuation(val: dict[str, Any], eff: dict[str, Any]) -> tuple[bool, list[str]]:
    """Doc §10.5: elegible solo si ev_view_net > 0 y ev_view_net / max_loss >= min_ev_ratio."""
    if val.get("error"):
        return False, [val["error"]]
    if val.get("ev_view_net") is None:
        return False, ["EV con sesgo no calculado (direccion APEX no verificada)"]
    reasons = []
    if val["ev_view_net"] <= 0:
        reasons.append(f"EV neto con sesgo {val['ev_view_net']:.2f} <= 0")
    if val.get("ev_ratio") is None or val["ev_ratio"] < eff["min_ev_ratio"]:
        reasons.append(f"EV/perdida maxima {val.get('ev_ratio')} < {eff['min_ev_ratio']}")
    if eff.get("require_ev_robust") and not val.get("ev_robust"):
        reasons.append("EV no es robusto ante escenarios adversos (sesgo reducido / ejecucion adversa / shock IV)")
    return (not reasons), reasons
