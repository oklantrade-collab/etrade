"""Modulo de Arbitraje Direccional y Resolucion de Conflictos para Catalizadores (doc S5-Cat).
Reglas:
1. ADX Override: Si ADX_5m >= adx_override (defecto 35, configurable), prevalece la direccion de ADX.
2. Arbitraje SIPV 1H: Si hay conflicto entre catalizadores (ej. ADX bajista vs REBOTE alcista)
   y ADX < 35, prevalece el estado de la vela 1H SIPV en formacion.
3. Zona de Indiferencia (Buffer Delta): Si la vela 1H esta dentro de [-Delta, +Delta] de indecision
   y hay conflicto, el resultado es NEUTRAL (NO_TRADE) para evitar trades forzados.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CatalystComponent:
    name: str                           # 'gap_go', 'sipv_basis_1h', 'adx_di_5m', 'rebote_15m'
    direction: Optional[str]            # 'bullish', 'bearish', None
    score: float                        # 0 a 100 o peso aportado
    triggered: bool                     # True si la condicion tecnica se cumplio
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArbitrationResolution:
    direction: Optional[str]            # 'bullish', 'bearish', None
    catalyst_score: float               # Score combinado (0 a 100)
    rule_applied: str                   # 'ADX_OVERRIDE', 'SIPV_1H_ARBITER', 'CONFLUENCE_DIRECT', 'NO_TRADE_CONFLICT'
    active_catalysts: list[str]         # nombres de los catalizadores activos que apoyan la direccion
    components: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def resolve_arbitration(
    components: list[CatalystComponent],
    sipv_1h_state: str,                 # 'bullish', 'bearish', 'neutral'
    adx_5m_value: float,
    adx_5m_dir: Optional[str],
    cfg: dict[str, Any],
) -> ArbitrationResolution:
    """Ejecuta el arbitraje y confluencia sobre los 4 catalizadores."""
    adx_override = float(cfg.get("catalyst_adx_override") or 35.0)
    min_score = float(cfg.get("catalyst_min_score") or 45.0)

    comp_map = {c.name: c for c in components}
    triggered = [c for c in components if c.triggered and c.direction]

    reasons: list[str] = []
    active_dirs = {c.direction for c in triggered if c.direction in ("bullish", "bearish")}

    # REGAL 1: OVERRIDE POR ADX >= 35 (Tendencia Explosiva)
    if adx_5m_value >= adx_override and adx_5m_dir in ("bullish", "bearish"):
        matching = [c.name for c in triggered if c.direction == adx_5m_dir]
        reasons.append(f"ADX 5m explosivo ({adx_5m_value:.1f} >= {adx_override:.0f}): prevalece direccion {adx_5m_dir}")
        score_base = max(70.0, min(100.0, 50.0 + (adx_5m_value - adx_override) * 2.0))
        return ArbitrationResolution(
            direction=adx_5m_dir,
            catalyst_score=score_base,
            rule_applied="ADX_OVERRIDE",
            active_catalysts=matching,
            components={c.name: c.__dict__ for c in components},
            reasons=reasons,
        )

    # REGLA 2: CONFLICTO ENTRE CATALIZADORES (ej. alcista vs bajista)
    if len(active_dirs) > 1:
        reasons.append(f"Conflicto de catalizadores detectado: direcciones {list(active_dirs)}")
        if sipv_1h_state in ("bullish", "bearish"):
            reasons.append(f"Arbitraje por Vela 1H SIPV: estado '{sipv_1h_state}' arbitra el conflicto")
            matching = [c.name for c in triggered if c.direction == sipv_1h_state]
            score_base = sum(c.score for c in triggered if c.direction == sipv_1h_state)
            if score_base < min_score:
                reasons.append(f"Score de confluencia con SIPV ({score_base:.1f}) < minimo requerido ({min_score:.1f})")
                return ArbitrationResolution(
                    direction=None,
                    catalyst_score=0.0,
                    rule_applied="SCORE_INSUFFICIENT_POST_ARBITRATION",
                    active_catalysts=matching,
                    components={c.name: c.__dict__ for c in components},
                    reasons=reasons,
                )
            return ArbitrationResolution(
                direction=sipv_1h_state,
                catalyst_score=min(100.0, score_base),
                rule_applied="SIPV_1H_ARBITER",
                active_catalysts=matching,
                components={c.name: c.__dict__ for c in components},
                reasons=reasons,
            )
        else:
            reasons.append("Vela 1H SIPV en zona neutral/indecision: NO_TRADE para evitar trades forzados")
            return ArbitrationResolution(
                direction=None,
                catalyst_score=0.0,
                rule_applied="NO_TRADE_CONFLICT_SIPV_NEUTRAL",
                active_catalysts=[],
                components={c.name: c.__dict__ for c in components},
                reasons=reasons,
            )

    # REGLA 3: SIN CONFLICTO (Unanimidad o solo una direccion activa)
    if len(active_dirs) == 1:
        unique_dir = list(active_dirs)[0]
        matching = [c.name for c in triggered if c.direction == unique_dir]
        total_score = sum(c.score for c in triggered if c.direction == unique_dir)
        # Bonus si la vela 1H SIPV coincide
        if sipv_1h_state == unique_dir:
            total_score += 15.0
            reasons.append(f"Vela 1H SIPV confirma direccion {unique_dir} (+15 pts)")

        final_score = min(100.0, round(total_score, 1))
        if final_score >= min_score:
            reasons.append(f"Confluencia limpia en direccion {unique_dir} (Score {final_score:.1f} >= {min_score:.1f})")
            return ArbitrationResolution(
                direction=unique_dir,
                catalyst_score=final_score,
                rule_applied="CONFLUENCE_DIRECT",
                active_catalysts=matching,
                components={c.name: c.__dict__ for c in components},
                reasons=reasons,
            )
        else:
            reasons.append(f"Score insuficiente ({final_score:.1f} < {min_score:.1f})")
            return ArbitrationResolution(
                direction=None,
                catalyst_score=final_score,
                rule_applied="SCORE_BELOW_MINIMUM",
                active_catalysts=matching,
                components={c.name: c.__dict__ for c in components},
                reasons=reasons,
            )

    # Sin catalizadores activos
    return ArbitrationResolution(
        direction=None,
        catalyst_score=0.0,
        rule_applied="NO_CATALYSTS_TRIGGERED",
        active_catalysts=[],
        components={c.name: c.__dict__ for c in components},
        reasons=["Ningun catalizador cumplio las condiciones de disparo"],
    )
