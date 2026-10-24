"""Black-Scholes minimo (sin dividendos, europeo). Se amplia en el Sprint 4 (repricing y escenarios)."""
from __future__ import annotations

import math


def _cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    return d1, d1 - sigma * math.sqrt(T)


def valid_inputs(S, K, T, sigma) -> bool:
    return all(v is not None for v in (S, K, T, sigma)) and S > 0 and K > 0 and T > 0 and sigma > 0


def bs_price(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float | None:
    if not valid_inputs(S, K, T, sigma):
        return None
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    if right == "C":
        return S * _cdf(d1) - K * math.exp(-r * T) * _cdf(d2)
    return K * math.exp(-r * T) * _cdf(-d2) - S * _cdf(-d1)


def bs_delta(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float | None:
    if not valid_inputs(S, K, T, sigma):
        return None
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return _cdf(d1) if right == "C" else _cdf(d1) - 1.0


def _pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float | None:
    if not valid_inputs(S, K, T, sigma):
        return None
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return _pdf(d1) / (S * sigma * math.sqrt(T))


def bs_vega(S: float, K: float, T: float, r: float, sigma: float) -> float | None:
    """Vega por 1 punto porcentual de volatilidad (0.01)."""
    if not valid_inputs(S, K, T, sigma):
        return None
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return S * math.sqrt(T) * _pdf(d1) * 0.01


def bs_theta(S: float, K: float, T: float, r: float, sigma: float, right: str) -> float | None:
    """Theta por dia (1/365)."""
    if not valid_inputs(S, K, T, sigma):
        return None
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    term1 = -(S * _pdf(d1) * sigma) / (2.0 * math.sqrt(T))
    if right == "C":
        term2 = -r * K * math.exp(-r * T) * _cdf(d2)
        return (term1 + term2) / 365.0
    term2 = r * K * math.exp(-r * T) * _cdf(-d2)
    return (term1 + term2) / 365.0


def compute_intraday_options_projection(
    underlying_price: float,
    target_price: float,
    strike: float,
    dte_days: float,
    iv: float,
    delta: float,
    gamma: float,
    spread_pct: float,
    rvol: float = 1.8,
    catalyst_multiplier: float = 1.0,
    right: str = "C"
) -> dict[str, float]:
    """
    Calcula la proyección matemática y probabilística de rentabilidad intradía:
      - p_touch_pct: Probabilidad aproximada de tocar el target durante la sesión.
      - projected_premium_delta: Ganancia proyectada de la prima por Delta + Gamma.
      - ev_score: Esperanza matemática combinada con RVOL, spread y catalizador.
    """
    dist = abs(target_price - underlying_price)
    atr_est = underlying_price * 0.01
    z = dist / max(1e-4, atr_est * 4.0)
    p_touch = min(95.0, max(15.0, 2.0 * (1.0 - _cdf(z)) * 100.0))

    ds = target_price - underlying_price if right == "C" else underlying_price - target_price
    # Expansión de Taylor: Delta * dS + 0.5 * Gamma * (dS^2)
    gamma_boost = 0.5 * abs(gamma) * (ds ** 2) if gamma > 0 else 0.0
    linear_gain = abs(delta) * max(0.0, ds)
    projected_premium_delta = linear_gain + gamma_boost

    spread_penalty = max(0.0, min(0.5, spread_pct / 100.0))
    ev = (p_touch / 100.0) * (projected_premium_delta) * (1.0 - spread_penalty) * min(2.5, rvol) * catalyst_multiplier

    return {
        "p_touch_pct": round(p_touch, 1),
        "projected_premium_delta": round(projected_premium_delta, 4),
        "ev_score": round(ev, 2)
    }
