"""
eTrade v7.0 — COST GUARD (Filtro de Costo de Transacción & Slippage Shield)
==========================================================================
Protege la rentabilidad neta eliminando pérdidas por fricción de spread Bid/Ask y comisiones:
1. Rechaza entradas en Stocks si el spread relativo (Ask - Bid) / Mid > 0.5%.
2. Exige que el movimiento esperado hacia el target (EMA20 o BB) sea al menos 3x el costo de ida y vuelta.
3. Provee cálculo de precios Limit Marketable (evita órdenes MKT destructivas en libros ilíquidos).
"""

from __future__ import annotations
from typing import Dict, Any, Tuple


def evaluate_stock_cost_feasibility(
    bid: float,
    ask: float,
    current_price: float,
    target_price: float,
    max_spread_pct: float = 0.50,
    min_reward_to_cost_ratio: float = 3.0
) -> Dict[str, Any]:
    """
    Evalúa la viabilidad de una operación en Stocks en función del costo del spread y el target esperado.
    """
    b = float(bid or 0.0)
    a = float(ask or 0.0)
    p = float(current_price or 0.0)
    t = float(target_price or 0.0)

    # Si no hay Bid/Ask explícito pero hay precio, estimar spread estándar
    if b <= 0 or a <= 0:
        b = p * 0.999
        a = p * 1.001

    mid = (b + a) / 2.0 if (b + a) > 0 else p
    if mid <= 0:
        return {"passed": False, "reason": "Precio o Mid inválido (<= 0)", "spread_pct": 0.0}

    spread_usd = a - b
    spread_pct = round((spread_usd / mid) * 100.0, 2)

    # 1. Filtro de ancho máximo de spread
    if spread_pct > max_spread_pct:
        return {
            "passed": False,
            "reason": f"Spread excesivo: {spread_pct:.2f}% > máx {max_spread_pct:.2f}% (Bid: ${b:.2f}, Ask: ${a:.2f})",
            "spread_pct": spread_pct,
            "mid_price": mid,
            "reward_cost_ratio": 0.0
        }

    # 2. Filtro de relación Ganancia Esperada vs Costo Roundtrip
    # Costo ida y vuelta = spread completo + 0.10% estimado de fees
    roundtrip_cost_pct = spread_pct + 0.10
    expected_gain_pct = ((t - mid) / mid * 100.0) if t > mid else 0.0
    reward_cost_ratio = round(expected_gain_pct / roundtrip_cost_pct, 2) if roundtrip_cost_pct > 0 else 0.0

    if t > mid and reward_cost_ratio < min_reward_to_cost_ratio:
        return {
            "passed": False,
            "reason": (
                f"Beneficio insuficiente vs costo: ratio {reward_cost_ratio}x < mín {min_reward_to_cost_ratio}x "
                f"(Ganancia est: +{expected_gain_pct:.1f}%, Costo roundtrip: {roundtrip_cost_pct:.2f}%)"
            ),
            "spread_pct": spread_pct,
            "mid_price": mid,
            "reward_cost_ratio": reward_cost_ratio
        }

    return {
        "passed": True,
        "reason": f"Costos viables: spread {spread_pct:.2f}%, ratio recompensa/costo {reward_cost_ratio}x",
        "spread_pct": spread_pct,
        "mid_price": mid,
        "reward_cost_ratio": reward_cost_ratio
    }


def calculate_limit_marketable_price(
    direction: str,
    bid: float,
    ask: float,
    current_price: float,
    tick_offset_cents: float = 0.01
) -> float:
    """
    Calcula un precio LMT agresivo (limit marketable) para garantizar fill sin regalar slippage de orden MKT.
    - Compra: min(ask, mid + 1 tick)
    - Venta: max(bid, mid - 1 tick)
    """
    b = float(bid or 0.0)
    a = float(ask or 0.0)
    p = float(current_price or 0.0)

    if b <= 0 or a <= 0:
        return round(p, 2)

    mid = (b + a) / 2.0
    side = direction.lower()

    if side == "buy":
        # Pagar como máximo el Ask o Mid + 1 centavo
        lmt = min(a, round(mid + tick_offset_cents, 2))
        return round(max(lmt, b), 2)
    else:
        # Vender como mínimo el Bid o Mid - 1 centavo
        lmt = max(b, round(mid - tick_offset_cents, 2))
        return round(min(lmt, a), 2)
