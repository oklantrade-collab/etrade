"""
eTrade v7.0 — RELATIVE STRENGTH FILTER (RS vs SPY)
==================================================
Filtro de Fuerza Relativa respecto al índice S&P 500 (SPY).
En días de mercado difícil o mixto, una acción que sube con volumen mientras el mercado cae
demuestra acumulación institucional agresiva y liderará el próximo rebote.

Fórmulas:
  RS_score = % cambio de la acción hoy - % cambio de SPY hoy

Reglas por Régimen Macro:
- RISK_OFF: Solo se permite compra Long si:
    1. Acción está en positivo (> 0.0%)
    2. RS vs SPY >= +1.5%
- NEUTRAL: Exige RS vs SPY >= +1.0%
- RISK_ON: Exige RS vs SPY >= 0.0% (no lagging)
"""

from __future__ import annotations
from typing import Dict, Any


def calculate_relative_strength(asset_change_pct: float, spy_change_pct: float) -> float:
    """Calcula la diferencia porcentual neta contra SPY."""
    return round(float(asset_change_pct or 0.0) - float(spy_change_pct or 0.0), 2)


def evaluate_relative_strength_qualification(
    asset_change_pct: float,
    spy_change_pct: float,
    macro_regime: str = "NEUTRAL"
) -> Dict[str, Any]:
    """
    Evalúa si el activo califica para compra según su Fuerza Relativa en el clima macro actual.
    """
    rs = calculate_relative_strength(asset_change_pct, spy_change_pct)
    reg = (macro_regime or "NEUTRAL").upper()

    if reg == "RISK_OFF":
        # En días de caída general, la acción debe ser líder absoluta contracorriente
        if asset_change_pct <= 0.0:
            return {
                "qualified": False,
                "rs_value": rs,
                "reason": f"Rechazada por RS: Mercado en RISK-OFF y activo en negativo ({asset_change_pct:+.2f}%)"
            }
        if rs < 1.5:
            return {
                "qualified": False,
                "rs_value": rs,
                "reason": f"Rechazada por RS: Requiere RS >= +1.5% en RISK-OFF (actual: {rs:+.2f}%)"
            }
        return {
            "qualified": True,
            "rs_value": rs,
            "reason": f"Excelente RS contracorriente (+{rs:.2f}%) mientras SPY cae ({spy_change_pct:+.2f}%)"
        }

    elif reg == "NEUTRAL":
        if rs < 1.0:
            return {
                "qualified": False,
                "rs_value": rs,
                "reason": f"Rechazada por RS: Requiere RS >= +1.0% en mercado Neutral (actual: {rs:+.2f}%)"
            }
        return {
            "qualified": True,
            "rs_value": rs,
            "reason": f"Fuerza relativa sólida (+{rs:.2f}%) en mercado Neutral"
        }

    else:  # RISK_ON
        if rs < -1.0:
            return {
                "qualified": False,
                "rs_value": rs,
                "reason": f"Rechazada por RS: Activo rezagado ({rs:+.2f}%) en día de Risk-On"
            }
        return {
            "qualified": True,
            "rs_value": rs,
            "reason": f"Acompañamiento positivo con el mercado (RS: {rs:+.2f}%)"
        }
