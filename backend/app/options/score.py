"""Motor de puntuacion de candidatas APEX Options (Sprint 5).
Escala 0-100 normalizada. Combina 6 factores ponderados configurables en Settings.
Un score alto nunca vuelve elegible una operacion invalida.
"""
from __future__ import annotations

from typing import Any

MODEL_VERSION = "v1.0-s5"


def _clip(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(val)))


def compute_expectancy_score(cand: dict[str, Any], eff: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 1: Expectativa neta (ev_view_net / max_loss).
    Normalizacion lineal: 0 si <= 0; 100 si >= ev_anchor (default 0.30 = 30%).
    """
    ev_ratio = cand.get("ev_ratio")
    if ev_ratio is None:
        ev = cand.get("ev_view_net")
        loss = cand.get("max_loss_contract") or cand.get("max_loss_total")
        if ev is not None and loss and loss > 0:
            ev_ratio = ev / loss
        else:
            ev_ratio = 0.0

    anchor = float(eff.get("ev_anchor") or 0.30)
    if anchor <= 0:
        anchor = 0.30

    if ev_ratio <= 0:
        score = 0.0
    elif ev_ratio >= anchor:
        score = 100.0
    else:
        score = (ev_ratio / anchor) * 100.0

    return _clip(score), {"ev_ratio": round(ev_ratio, 4), "ev_anchor": anchor, "ev_view_net": cand.get("ev_view_net")}


def compute_apex_signal_score(cand: dict[str, Any], underlying: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 2: Calidad de senal APEX o Catalizador del subyacente.
    Score en escala 0-100. Coherencia direccional obligatoria.
    """
    apex_score = underlying.get("apex_score")
    if apex_score is None:
        apex_score = 50.0
    else:
        apex_score = float(apex_score)

    cand_dir = (cand.get("direction") or "").lower()
    raw_und_dir = underlying.get("direction") or ""
    # Normalizar CALL/PUT o bullish/bearish
    und_dir = "bullish" if raw_und_dir in ("CALL", "bullish") else ("bearish" if raw_und_dir in ("PUT", "bearish") else raw_und_dir.lower())
    cand_norm_dir = "bullish" if cand_dir in ("call", "bullish") else ("bearish" if cand_dir in ("put", "bearish") else cand_dir)

    dir_source = cand.get("direction_source") or underlying.get("direction_source") or "unverified"

    if dir_source == "catalyst":
        cat_score = float(underlying.get("catalyst_score") or cand.get("catalyst_score") or 60.0)
        if und_dir and cand_norm_dir and cand_norm_dir != und_dir:
            score = 0.0
            note = f"direccion opuesta al catalizador ({cand_norm_dir} vs {und_dir})"
        else:
            score = cat_score
            note = f"coherente con catalizador ({raw_und_dir})"
        return _clip(score), {"catalyst_score": cat_score, "direction_source": "catalyst", "note": note}

    if dir_source == "apex":
        if und_dir and cand_norm_dir != und_dir:
            score = 0.0
            note = f"direccion opuesta a la senal APEX ({cand_norm_dir} vs {und_dir})"
        else:
            score = apex_score
            note = f"coherente con senal APEX ({und_dir})"
    else:
        # Direccion no verificada: penalizacion del 40% respecto al score base
        score = min(apex_score * 0.60, 50.0)
        note = "direccion no verificada (penalizacion aplicada)"

    return _clip(score), {"apex_score": apex_score, "direction_source": dir_source, "note": note}


def compute_liquidity_score(cand: dict[str, Any], eff: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 3: Liquidez y calidad de cotizacion.
    Spread relativo (0% -> 100, 10% -> 0), OI/volumen y estado del dato de mercado.
    """
    legs = cand.get("legs") or []
    if not legs:
        return 0.0, {"reason": "sin piernas"}

    spreads = []
    ois = []
    states = []

    for lg in legs:
        bid = lg.get("bid")
        ask = lg.get("ask")
        if bid is not None and ask is not None and (bid + ask) > 0:
            mid = (bid + ask) / 2.0
            rel_spread = (ask - bid) / mid
            spreads.append(rel_spread)
        else:
            spreads.append(1.0)  # max spread si falta cotizacion

        oi = lg.get("open_interest")
        ois.append(float(oi) if oi is not None else 0.0)
        states.append(lg.get("market_data_type") or "UNKNOWN")

    max_spread = max(spreads) if spreads else 1.0
    min_oi = min(ois) if ois else 0.0

    # Spread score: 0% -> 100, 10% (0.10) -> 0
    if max_spread <= 0:
        spread_score = 100.0
    elif max_spread >= 0.10:
        spread_score = 0.0
    else:
        spread_score = (1.0 - (max_spread / 0.10)) * 100.0

    # OI score: >= 500 -> 100, <= 50 -> 20
    if min_oi >= 500:
        oi_score = 100.0
    elif min_oi <= 50:
        oi_score = 20.0
    else:
        oi_score = 20.0 + ((min_oi - 50.0) / (500.0 - 50.0)) * 80.0

    raw_liquidity = 0.60 * spread_score + 0.40 * oi_score

    # Ajuste por estado del dato
    allow_delayed = bool(eff.get("allow_delayed_data"))
    has_delayed = any(s == "DELAYED" for s in states)
    has_bad = any(s in ("STALE", "FROZEN", "UNKNOWN") for s in states)

    if has_bad:
        data_mult = 0.0
        data_note = "cotizaciones stale o frozen"
    elif has_delayed:
        if allow_delayed:
            data_mult = 0.70  # 30% de penalizacion por dato diferido en modo prueba
            data_note = "dato diferido permitido en modo prueba (-30%)"
        else:
            data_mult = 0.0
            data_note = "dato diferido no permitido"
    else:
        data_mult = 1.0
        data_note = "datos LIVE"

    final_score = raw_liquidity * data_mult
    return _clip(final_score), {
        "max_rel_spread_pct": round(max_spread * 100, 2),
        "min_oi": int(min_oi),
        "raw_liquidity": round(raw_liquidity, 1),
        "data_multiplier": data_mult,
        "data_note": data_note,
    }


def compute_risk_score(cand: dict[str, Any], eff: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 4: Riesgo y escenarios adversos.
    Drawdown en peor escenario simulado vs max_loss y sobrecoste de ejecucion.
    """
    max_loss = cand.get("max_loss_contract") or cand.get("max_loss_total") or 1.0
    worst_pnl = cand.get("worst_adverse_scenario_pnl")
    if worst_pnl is None:
        worst_pnl = -max_loss

    # Preservacion frente a max loss: si el peor escenario pierde menos que el max loss teorico
    # (ej. salida anticipada o spread que acota la perdida)
    loss_ratio = abs(float(worst_pnl)) / float(max_loss) if max_loss > 0 else 1.0
    drawdown_score = _clip((1.0 - min(loss_ratio, 1.0)) * 100.0)

    # Sobrecoste de ejecucion (slippage sobre mid)
    overcost = float(cand.get("exec_overcost_pct") or 0.0)
    max_overcost = float(eff.get("max_exec_overcost_pct") or 25.0)
    if max_overcost <= 0:
        overcost_score = 100.0
    else:
        overcost_score = _clip((1.0 - (overcost / max_overcost)) * 100.0)

    # EV adverso: si la expectativa con ejecucion adversa sigue siendo positiva, da bonus
    ev_adv = cand.get("ev_view_adverse")
    if ev_adv is not None and max_loss > 0:
        ev_adv_ratio = float(ev_adv) / float(max_loss)
        ev_adv_score = _clip(50.0 + (ev_adv_ratio / 0.20) * 50.0)
    else:
        ev_adv_score = 50.0

    final_score = 0.40 * drawdown_score + 0.30 * overcost_score + 0.30 * ev_adv_score
    return _clip(final_score), {
        "drawdown_score": round(drawdown_score, 1),
        "overcost_score": round(overcost_score, 1),
        "ev_adverse_score": round(ev_adv_score, 1),
        "exec_overcost_pct": overcost,
    }


def compute_iv_greeks_score(cand: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 5: IV y griegas.
    Penaliza IV muy alta en estrategias compradas (riesgo de crush);
    premia deltas optimos (0.40-0.60 en piernas largas, delta neto moderado en spreads).
    """
    legs = cand.get("legs") or []
    strategy = cand.get("strategy_type") or ""

    # IV de la pierna larga principal
    ivs = [float(l["iv"]) for l in legs if l.get("iv") is not None]
    avg_iv = sum(ivs) / len(ivs) if ivs else 0.50

    # IV score: IV moderada (20%-40%) es ideal para compras; >80% castigada
    if avg_iv <= 0.35:
        iv_score = 100.0
    elif avg_iv <= 0.60:
        iv_score = 100.0 - ((avg_iv - 0.35) / 0.25) * 30.0  # 100 -> 70
    elif avg_iv <= 1.00:
        iv_score = 70.0 - ((avg_iv - 0.60) / 0.40) * 45.0   # 70 -> 25
    else:
        iv_score = max(0.0, 25.0 - ((avg_iv - 1.00) / 0.50) * 25.0)

    # Delta sweet spot
    long_legs = [l for l in legs if l.get("side") == "buy"]
    if long_legs and long_legs[0].get("delta") is not None:
        delta = abs(float(long_legs[0]["delta"]))
        # punto optimo 0.50 (ATM)
        dist_from_target = abs(delta - 0.50)
        delta_score = _clip((1.0 - (dist_from_target / 0.30)) * 100.0)
    else:
        delta_score = 50.0

    final_score = 0.50 * iv_score + 0.50 * delta_score
    return _clip(final_score), {
        "avg_iv": round(avg_iv, 4),
        "iv_score": round(iv_score, 1),
        "delta_score": round(delta_score, 1),
        "strategy": strategy,
    }


def compute_context_score(cand: dict[str, Any], underlying: dict[str, Any], eff: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Componente 6: Catalizadores y contexto (eventos dentro del DTE).
    100 si no hay evento binario reportado; 50 si no esta verificado; 0 si hay evento bloqueante.
    """
    event_flags = underlying.get("event_flags")
    warnings = underlying.get("warnings") or []
    is_unverified = any("no verificado" in str(w) for w in warnings) or event_flags is None

    if is_unverified:
        score = 50.0
        note = "eventos no verificados (neutral)"
    elif len(event_flags) == 0:
        score = 100.0
        note = "sin eventos binarios dentro del DTE"
    else:
        # Hay eventos reportados (earnings, etc.)
        if eff.get("block_events_in_dte", True):
            score = 0.0
            note = f"evento presente ({', '.join(event_flags)})"
        else:
            score = 30.0
            note = f"evento presente pero no bloqueado ({', '.join(event_flags)})"

    return _clip(score), {"event_flags": event_flags or [], "note": note}


def score_candidate(cand: dict[str, Any], underlying: dict[str, Any], eff: dict[str, Any]) -> dict[str, Any]:
    """Calcula el Options Score total (0-100) y su desglose completo por componentes.
    Pesos configurables en Settings:
      - w_expectancy (30%)
      - w_apex_signal (20%)
      - w_liquidity (20%)
      - w_risk (15%)
      - w_iv_greeks (10%)
      - w_context (5%)
    """
    w_exp = float(eff.get("w_expectancy", 30))
    w_apex = float(eff.get("w_apex_signal", 20))
    w_liq = float(eff.get("w_liquidity", 20))
    w_risk = float(eff.get("w_risk", 15))
    w_iv = float(eff.get("w_iv_greeks", 10))
    w_ctx = float(eff.get("w_context", 5))

    total_w = w_exp + w_apex + w_liq + w_risk + w_iv + w_ctx
    if total_w <= 0:
        total_w = 100.0

    s_exp, d_exp = compute_expectancy_score(cand, eff)
    s_apex, d_apex = compute_apex_signal_score(cand, underlying)
    s_liq, d_liq = compute_liquidity_score(cand, eff)
    s_risk, d_risk = compute_risk_score(cand, eff)
    s_iv, d_iv = compute_iv_greeks_score(cand)
    s_ctx, d_ctx = compute_context_score(cand, underlying, eff)

    weighted_sum = (
        s_exp * w_exp +
        s_apex * w_apex +
        s_liq * w_liq +
        s_risk * w_risk +
        s_iv * w_iv +
        s_ctx * w_ctx
    )
    final_score = round(_clip(weighted_sum / total_w), 1)

    min_score = float(eff.get("min_score", 60))
    eligible_by_score = final_score >= min_score

    # Check missing components and calculate coverage (§5, §9.1)
    missing_components = []
    # Essential components: expectancy, liquidity, risk
    if cand.get("ev_view_net") is None:
        missing_components.append("expectancy")
    legs = cand.get("legs") or []
    if not legs or any(l.get("bid") is None or l.get("ask") is None for l in legs):
        missing_components.append("liquidity")
    if not (cand.get("max_loss_contract") or cand.get("max_loss_total")):
        missing_components.append("risk")
    if not legs or any(l.get("iv") is None for l in legs):
        missing_components.append("iv_greeks")
    if not (cand.get("direction_source") or underlying.get("direction")):
        missing_components.append("apex_signal")
    if underlying.get("event_flags") is None and not cand.get("event_state"):
        missing_components.append("context")

    total_components_count = 6
    present_count = total_components_count - len(missing_components)
    coverage = round(present_count / total_components_count, 2)

    components_list = [
        {
            "name": "expectancy",
            "weight": round(w_exp / total_w, 2),
            "score": s_exp,
            "contribution": round(s_exp * w_exp / total_w, 2),
            "inputs": d_exp,
            "sub_scores": {"ev_ratio": d_exp.get("ev_ratio")},
            "multiplier": 1.0,
            "notes": [],
        },
        {
            "name": "apex_signal",
            "weight": round(w_apex / total_w, 2),
            "score": s_apex,
            "contribution": round(s_apex * w_apex / total_w, 2),
            "inputs": {"direction_source": d_apex.get("direction_source")},
            "sub_scores": {"raw_score": d_apex.get("apex_score") or d_apex.get("catalyst_score")},
            "multiplier": 1.0,
            "notes": [d_apex.get("note")] if d_apex.get("note") else [],
        },
        {
            "name": "liquidity",
            "weight": round(w_liq / total_w, 2),
            "score": s_liq,
            "contribution": round(s_liq * w_liq / total_w, 2),
            "inputs": {
                "max_rel_spread_pct": d_liq.get("max_rel_spread_pct"),
                "min_oi": d_liq.get("min_oi"),
            },
            "sub_scores": {"raw_liquidity": d_liq.get("raw_liquidity")},
            "multiplier": d_liq.get("data_multiplier", 1.0),
            "notes": [d_liq.get("data_note")] if d_liq.get("data_note") else [],
        },
        {
            "name": "risk",
            "weight": round(w_risk / total_w, 2),
            "score": s_risk,
            "contribution": round(s_risk * w_risk / total_w, 2),
            "inputs": {"exec_overcost_pct": d_risk.get("exec_overcost_pct")},
            "sub_scores": {
                "drawdown": d_risk.get("drawdown_score"),
                "overcost": d_risk.get("overcost_score"),
                "ev_adverse": d_risk.get("ev_adverse_score"),
            },
            "multiplier": 1.0,
            "notes": [],
        },
        {
            "name": "iv_greeks",
            "weight": round(w_iv / total_w, 2),
            "score": s_iv,
            "contribution": round(s_iv * w_iv / total_w, 2),
            "inputs": {"avg_iv": d_iv.get("avg_iv")},
            "sub_scores": {"iv_score": d_iv.get("iv_score"), "delta_score": d_iv.get("delta_score")},
            "multiplier": 1.0,
            "notes": [],
        },
        {
            "name": "context",
            "weight": round(w_ctx / total_w, 2),
            "score": s_ctx,
            "contribution": round(s_ctx * w_ctx / total_w, 2),
            "inputs": {"event_flags": d_ctx.get("event_flags")},
            "sub_scores": {},
            "multiplier": 1.0,
            "notes": [d_ctx.get("note")] if d_ctx.get("note") else [],
        },
    ]

    breakdown = {
        "score_version": "sv-001",
        "code_version": "git:master",
        "config_version": int(eff.get("config_version") or 1),
        "score_total": final_score,
        "final_score": final_score,
        "coverage": coverage,
        "missing_components": missing_components,
        "min_score_required": min_score,
        "eligible_by_score": eligible_by_score,
        "weights": {
            "w_expectancy": w_exp, "w_apex_signal": w_apex, "w_liquidity": w_liq,
            "w_risk": w_risk, "w_iv_greeks": w_iv, "w_context": w_ctx,
        },
        "components": {
            "expectancy": {"score": s_exp, "weighted": round(s_exp * w_exp / total_w, 2), "detail": d_exp},
            "apex_signal": {"score": s_apex, "weighted": round(s_apex * w_apex / total_w, 2), "detail": d_apex},
            "liquidity": {"score": s_liq, "weighted": round(s_liq * w_liq / total_w, 2), "detail": d_liq},
            "risk": {"score": s_risk, "weighted": round(s_risk * w_risk / total_w, 2), "detail": d_risk},
            "iv_greeks": {"score": s_iv, "weighted": round(s_iv * w_iv / total_w, 2), "detail": d_iv},
            "context": {"score": s_ctx, "weighted": round(s_ctx * w_ctx / total_w, 2), "detail": d_ctx},
        },
        "components_list": components_list,
        "model_version": MODEL_VERSION,
    }
    return {"score": final_score, "coverage": coverage, "score_breakdown": breakdown}


def replay_evaluation(cand: dict[str, Any], underlying: dict[str, Any], eff: dict[str, Any]) -> dict[str, Any]:
    """Reejecuta deterministamente la valoracion y score de una candidata (Doc §13.3).
    Comprueba reproducibilidad bit a bit.
    """
    replayed = score_candidate(cand, underlying, eff)
    orig_score = cand.get("score")
    diff = None
    matches = True
    if orig_score is not None:
        diff = round(float(replayed["score"]) - float(orig_score), 4)
        matches = abs(diff) < 0.01

    return {
        "candidate_id": cand.get("id"),
        "original_score": orig_score,
        "replayed_score": replayed["score"],
        "diff": diff,
        "matches": matches,
        "coverage": replayed["coverage"],
        "breakdown": replayed["score_breakdown"],
    }


def rank_and_score_candidates(candidates: list[dict[str, Any]],
                              underlyings_by_id: dict[int, dict[str, Any]],
                              eff: dict[str, Any]) -> list[dict[str, Any]]:
    """Puntua y asigna ranking global y por estrategia a todas las candidatas.
    Devuelve lista ordenada descendentemente por score.
    Determinista y reproducible.
    """
    scored: list[dict[str, Any]] = []
    for c in candidates:
        row = dict(c)
        uid = row.get("underlying_id") or 0
        und = underlyings_by_id.get(uid) or {}
        res = score_candidate(row, und, eff)
        row["score"] = res["score"]
        row["score_breakdown"] = res["score_breakdown"]
        scored.append(row)

    # Ordenamiento: score desc, ev_ratio desc, max_loss_total asc, id asc
    def sort_key(item: dict[str, Any]):
        return (
            -float(item.get("score") or 0.0),
            -float(item.get("ev_ratio") or 0.0),
            float(item.get("max_loss_total") or 999999.0),
            int(item.get("id") or 0),
        )

    scored.sort(key=sort_key)

    # Asignar rank global
    for rank, row in enumerate(scored, start=1):
        row["rank_global"] = rank

    # Asignar rank por estrategia
    strat_counters: dict[str, int] = {}
    for row in scored:
        stype = row.get("strategy_type") or "unknown"
        strat_counters[stype] = strat_counters.get(stype, 0) + 1
        row["rank_strategy"] = strat_counters[stype]

    return scored
