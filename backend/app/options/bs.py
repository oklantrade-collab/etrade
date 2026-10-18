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
