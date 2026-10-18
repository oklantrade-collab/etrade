"""Selector de Cartera APEX Options (Sprint 5).
Seleccion greedy por Options Score sujeta a restricciones de riesgo, direccion y subyacente.
Reglas (§11.1 y §12):
  1. Maximo 1 posicion por subyacente.
  2. Maximo 2 posiciones en la misma direccion (bullish / bearish).
  3. Suma de max_loss <= riesgo abierto restante (presupuesto agregado).
  4. Riesgo por operacion individual <= max_risk_per_trade_usd (50-100 USD).
  5. Stop diario activado bloquea toda seleccion hasta la siguiente sesion.
  6. Si una candidata con qty > 1 excede el riesgo restante, adapta qty hacia abajo si cabe.
  7. Minimo Options Score (default >= 60).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from app.options import options_aduana as aduana

MODEL_VERSION = "v1.0-s5"


@dataclass
class SelectionResult:
    selected: list[dict[str, Any]]
    skipped: list[dict[str, Any]]
    total_risk_allocated: float
    remaining_budget: float
    initial_budget: float
    used_open_risk: float
    daily_stop_triggered: bool
    stop_reason: str | None
    model_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def select_portfolio(candidates: list[dict[str, Any]],
                     existing_positions: list[aduana.OpenPosition] | list[dict[str, Any]],
                     eff: dict[str, Any],
                     realized_pnl_today: float = 0.0,
                     unrealized_pnl_today: float = 0.0) -> SelectionResult:
    """Ejecuta el algoritmo de seleccion greedy con restricciones."""
    # 1. Normalizar posiciones existentes
    open_pos: list[aduana.OpenPosition] = []
    for p in existing_positions:
        if isinstance(p, aduana.OpenPosition):
            open_pos.append(p)
        elif isinstance(p, dict):
            open_pos.append(aduana.OpenPosition(
                underlying_id=p.get("underlying_id") or p.get("symbol_id") or 0,
                max_loss_total=float(p.get("max_loss_total") or p.get("risk_total") or 0.0),
                direction=str(p.get("direction") or "neutral"),
            ))

    # 2. Verificar stop diario (§12.2)
    daily_stop_usd = float(eff.get("daily_stop_usd") or 50.0)
    current_pnl_today = realized_pnl_today + unrealized_pnl_today
    if current_pnl_today <= -daily_stop_usd:
        reason = f"Stop diario activado: PnL de hoy (${current_pnl_today:.2f}) <= -${daily_stop_usd:.2f}"
        return SelectionResult(
            selected=[],
            skipped=[{"candidate_id": c.get("id"), "symbol": c.get("symbol"), "reason": reason} for c in candidates],
            total_risk_allocated=0.0,
            remaining_budget=0.0,
            initial_budget=float(eff.get("max_open_risk_usd") or 100.0),
            used_open_risk=sum(p.max_loss_total for p in open_pos),
            daily_stop_triggered=True,
            stop_reason=reason,
            model_version=MODEL_VERSION,
        )

    # 3. Presupuesto de riesgo abierto
    max_open_risk = float(eff.get("max_open_risk_usd") or 100.0)
    used_risk = sum(p.max_loss_total for p in open_pos)
    remaining_budget = max(0.0, max_open_risk - used_risk)

    max_per_trade = float(eff.get("max_risk_per_trade_usd") or 50.0)
    max_daily_sel = int(eff.get("max_daily_selections") or 3)
    max_per_underlying = int(eff.get("max_positions_per_underlying") or 1)
    max_same_dir = int(eff.get("max_same_direction") or 2)
    min_score = float(eff.get("min_score") or 60.0)

    # Contabilidad inicial del portafolio existente
    used_underlyings = set(p.underlying_id for p in open_pos)
    direction_counts = Counter(p.direction for p in open_pos)

    # 4. Filtrar y ordenar candidatas elegibles
    # Solo entran candidatas aprobadas por ADUANA/valoracion ('eligible') y con score >= min_score
    eligible = [c for c in candidates if c.get("eligibility_status") in ("eligible", "pending")]
    # Ordenamiento greedy: score descendente, ev_ratio desc, max_loss_total asc, id asc
    sorted_candidates = sorted(
        eligible,
        key=lambda x: (
            -float(x.get("score") or 0.0),
            -float(x.get("ev_ratio") or 0.0),
            float(x.get("max_loss_total") or 999999.0),
            int(x.get("id") or 0),
        ),
    )

    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for cand in sorted_candidates:
        cid = cand.get("id")
        uid = cand.get("underlying_id")
        direction = cand.get("direction")
        score = float(cand.get("score") or 0.0)
        loss_total = float(cand.get("max_loss_total") or 0.0)
        contract_loss = float(cand.get("max_loss_contract") or loss_total)
        qty = int(cand.get("qty") or 1)

        # Regla 0: Score minimo
        if score < min_score:
            skipped.append({
                "candidate_id": cid, "underlying_id": uid, "score": score,
                "reason": f"Options Score ({score:.1f}) inferior al minimo requerido ({min_score:.1f})",
            })
            continue

        # Regla 1: Maximo de selecciones diarias
        if len(selected) >= max_daily_sel:
            skipped.append({
                "candidate_id": cid, "underlying_id": uid, "score": score,
                "reason": f"Cupo diario de selecciones alcanzado (maximo {max_daily_sel})",
            })
            continue

        # Regla 2: Maximo 1 posicion/seleccion por subyacente
        if uid in used_underlyings:
            skipped.append({
                "candidate_id": cid, "underlying_id": uid, "score": score,
                "reason": f"Subyacente (id {uid}) ya tiene posicion o seleccion activa (limite: {max_per_underlying})",
            })
            continue

        # Regla 3: Maximo en la misma direccion
        if direction and direction_counts[direction] >= max_same_dir:
            skipped.append({
                "candidate_id": cid, "underlying_id": uid, "score": score,
                "reason": f"Limite de {max_same_dir} posiciones en direccion '{direction}' alcanzado",
            })
            continue

        # Regla 4: Riesgo por operacion individual
        if loss_total > max_per_trade:
            # Si tiene qty > 1, intentamos reducirla para que entre en el limite por trade
            if qty > 1 and contract_loss <= max_per_trade:
                new_qty = int(max_per_trade // contract_loss)
                if new_qty >= 1:
                    qty = new_qty
                    loss_total = round(contract_loss * qty, 2)
                else:
                    skipped.append({
                        "candidate_id": cid, "underlying_id": uid, "score": score,
                        "reason": f"Riesgo individual (${loss_total:.2f}) supera maximo (${max_per_trade:.2f})",
                    })
                    continue
            else:
                skipped.append({
                    "candidate_id": cid, "underlying_id": uid, "score": score,
                    "reason": f"Riesgo individual (${loss_total:.2f}) supera maximo (${max_per_trade:.2f})",
                })
                continue

        # Regla 5: Presupuesto abierto restante
        if loss_total > remaining_budget:
            # Intento de adaptacion de tamano hacia abajo (§11.1 regla 4)
            if qty > 1 and contract_loss <= remaining_budget:
                new_qty = int(remaining_budget // contract_loss)
                if new_qty >= 1:
                    qty = new_qty
                    loss_total = round(contract_loss * qty, 2)
                    cand = dict(cand, qty=qty, max_loss_total=loss_total,
                                budget_adapted=True,
                                adaptation_note=f"Cantidad reducida a {qty} para entrar en el presupuesto restante (${remaining_budget:.2f})")
                else:
                    skipped.append({
                        "candidate_id": cid, "underlying_id": uid, "score": score,
                        "reason": f"Riesgo (${loss_total:.2f}) excede presupuesto restante (${remaining_budget:.2f})",
                    })
                    continue
            else:
                skipped.append({
                    "candidate_id": cid, "underlying_id": uid, "score": score,
                    "reason": f"Riesgo (${loss_total:.2f}) excede presupuesto restante (${remaining_budget:.2f})",
                })
                continue

        # Cumple todas las restricciones: seleccionada
        sel_cand = dict(cand)
        sel_cand["qty"] = qty
        sel_cand["max_loss_total"] = loss_total
        sel_cand["selected_order"] = len(selected) + 1

        selected.append(sel_cand)
        used_underlyings.add(uid)
        if direction:
            direction_counts[direction] += 1
        remaining_budget -= loss_total

    total_allocated = sum(float(c.get("max_loss_total") or 0.0) for c in selected)

    return SelectionResult(
        selected=selected,
        skipped=skipped,
        total_risk_allocated=round(total_allocated, 2),
        remaining_budget=round(remaining_budget, 2),
        initial_budget=max_open_risk,
        used_open_risk=round(used_risk, 2),
        daily_stop_triggered=False,
        stop_reason=None,
        model_version=MODEL_VERSION,
    )
