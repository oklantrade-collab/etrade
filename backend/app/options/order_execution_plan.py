"""
Plan de Ejecución Escalonada (Single-Order Adaptive Ladder / Chaser) para IB/TWS.

Evita el riesgo de doble llenado y bloqueo de capital de enviar 2 órdenes
simultáneas para una misma señal, reemplazándolo por:
1. Precio límite inicial guiado por RVOL y Spread (más agresivo con RVOL alto).
2. Re-cotización controlada (chaser) dentro de un techo máximo de slippage.
3. TTL estricto en TWS para cancelar órdenes no ejecutadas sin dejar colgadas.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any, Dict


def snap_option_tick(price: float, mode: str = "nearest") -> float:
    """Snap option price to valid OPRA/TWS tick increments ($0.05 if >= $3.00, else $0.01)."""
    p = max(0.01, float(price or 0.01))
    tick = Decimal("0.05") if p >= 3.0 else Decimal("0.01")
    d_price = Decimal(f"{p:.4f}")
    rounding = ROUND_CEILING if mode == "ceil" else (ROUND_FLOOR if mode == "floor" else ROUND_HALF_UP)
    steps = (d_price / tick).to_integral_value(rounding=rounding)
    snapped = float(steps * tick)
    return round(max(0.01, snapped), 2)


def compute_option_entry_plan(
    bid: float,
    ask: float,
    mid: float,
    rvol: float = 1.0,
) -> Dict[str, Any]:
    """
    Calcula el plan inicial de entrada LMT para una compra de opción según RVOL y spread.

    - RVOL >= 2.0 (momentum fuerte): entra agresivo cerca del Ask (Mid + 75% spread),
      Adaptive Urgent, re-cotiza a los 15s y expira a los 45s.
    - RVOL >= 1.3 (momentum moderado): entra en Mid + 50% spread,
      Adaptive Normal, re-cotiza a los 20s y expira a los 60s.
    - RVOL < 1.3 (calma): entra en Mid + 25% spread,
      Adaptive Normal, re-cotiza a los 20s y expira a los 60s.
    """
    b = max(0.0, float(bid or 0.0))
    a = max(0.0, float(ask or 0.0))
    m = max(0.0, float(mid or 0.0))
    rv = max(0.0, float(rvol or 1.0))

    if rv >= 2.0:
        spread_ratio = 0.75
        adaptive_priority = "Urgent"
        reprice_after_sec = 15.0
        ttl_sec = 45.0
        tier = "HIGH_RVOL"
    elif rv >= 1.3:
        spread_ratio = 0.50
        adaptive_priority = "Normal"
        reprice_after_sec = 20.0
        ttl_sec = 60.0
        tier = "MED_RVOL"
    else:
        spread_ratio = 0.25
        adaptive_priority = "Normal"
        reprice_after_sec = 20.0
        ttl_sec = 60.0
        tier = "LOW_RVOL"

    if b > 0 and a > 0 and a >= b:
        spread = a - b
        mid_val = (b + a) / 2.0
        spread_pct = round((spread / mid_val * 100.0), 2) if mid_val > 0 else 0.0
        raw_lmt = min(a, mid_val + (spread * spread_ratio))
        limit_price = snap_option_tick(max(0.01, raw_lmt), mode="nearest")
        max_chase_price = snap_option_tick(max(a * 1.05, limit_price + max(0.05, spread * 0.50)), mode="ceil")
    else:
        ref = a if a > 0 else (m if m > 0 else (b if b > 0 else 0.05))
        spread_pct = 0.0
        limit_price = snap_option_tick(max(0.01, ref), mode="nearest")
        max_chase_price = snap_option_tick(max(limit_price + 0.05, limit_price * 1.05), mode="ceil")

    return {
        "limit_price": limit_price,
        "max_chase_price": max_chase_price,
        "adaptive_priority": adaptive_priority,
        "reprice_after_sec": reprice_after_sec,
        "ttl_sec": ttl_sec,
        "rvol": round(rv, 2),
        "tier": tier,
        "spread_pct": spread_pct,
    }


def compute_reprice_limit(
    current_lmt: float,
    max_chase_price: float,
    live_bid: float = 0.0,
    live_ask: float = 0.0,
    reprice_count: int = 0,
) -> Dict[str, Any]:
    """
    Evalúa el siguiente escalón de precio para una orden BUY abierta en TWS.

    Respeta el tick mínimo legal ($0.05 si prima >= $3.00, $0.01 si < $3.00).
    Retorna dict con `action` in {'replace', 'cancel_chase_exceeded', 'hold'}.
    """
    cur = max(0.01, float(current_lmt or 0.01))
    cap_raw = max(cur, float(max_chase_price or cur * 1.05))
    cap = snap_option_tick(cap_raw, mode="floor") if cap_raw >= 3.0 else round(cap_raw, 2)
    b = max(0.0, float(live_bid or 0.0))
    a = max(0.0, float(live_ask or 0.0))
    tick = 0.05 if cur >= 3.0 else 0.01

    if a > 0:
        if a > cap_raw:
            return {
                "action": "cancel_chase_exceeded",
                "new_lmt": cur,
                "reason": f"Ask actual ${a:.2f} supera techo max_chase ${cap_raw:.2f}",
            }
        # En el 2do intento, permitir +1 tick sobre Ask si sigue dentro del techo
        nudge = tick if reprice_count >= 1 else 0.0
        raw_cand = max(cur + tick, a + nudge)
        snapped = snap_option_tick(raw_cand, mode="ceil") if raw_cand >= 3.0 else round(raw_cand, 2)
        candidate = min(cap, snapped)
        if b > 0 and b <= a and candidate < b:
            snapped_a = snap_option_tick(a, mode="nearest") if a >= 3.0 else round(a, 2)
            candidate = min(cap, snapped_a)
    else:
        step = max(tick * 2.0, round(cur * 0.02, 2))
        raw_cand = cur + step
        candidate = snap_option_tick(raw_cand, mode="ceil") if raw_cand >= 3.0 else round(raw_cand, 2)
        if candidate > cap_raw:
            return {
                "action": "cancel_chase_exceeded",
                "new_lmt": cur,
                "reason": f"Re-cotización ${candidate:.2f} supera techo max_chase ${cap_raw:.2f}",
            }

    if candidate <= cur:
        return {
            "action": "hold",
            "new_lmt": cur,
            "reason": "Límite actual ya cubre o supera el Ask disponible",
        }

    return {
        "action": "replace",
        "new_lmt": round(candidate, 2),
        "reason": f"Escalando LMT de ${cur:.2f} -> ${candidate:.2f} (cap ${cap:.2f})",
    }
