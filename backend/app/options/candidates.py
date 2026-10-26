"""Generacion y persistencia de candidatas (Sprint 3). Lee contratos/cotizaciones guardados; NO usa IBKR."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

from app.core.logger import log_info
from app.options import options_aduana as aduana
from app.options import portfolio_selector as sel
from app.options import score as sc
from app.options import strategies as st
from app.options import valuation as val_

MODULE = "OPTIONS_CAND"
MODEL_VERSION = "v1.0-s5"

MAX_REJECTED_SAMPLE = 25         # muestra de descartes por subyacente (resto se resume en conteos)


def _to_quote(c: dict[str, Any]) -> st.Q:
    ql = c.get("opt_quotes_latest") or {}
    if isinstance(ql, list):
        ql = ql[0] if ql else {}
    f = lambda k: (float(ql[k]) if ql.get(k) is not None else None)  # noqa: E731  (NULL se conserva)
    return st.Q(
        contract_id=c["id"], conid=c["conid"], right=c["right"], strike=float(c["strike"]),
        expiry=date.fromisoformat(c["expiry"]), bid=f("bid"), ask=f("ask"), volume=f("volume"),
        open_interest=f("open_interest"), iv=f("iv"), delta=f("delta"),
        usable=bool(ql.get("usable")), unusable_reason=ql.get("unusable_reason"),
        market_data_type=ql.get("market_data_type"), multiplier=int(c.get("multiplier") or 100),
    )


def candidate_row(c: st.Candidate, underlying_id: int, direction_source: str, settings_version: int,
                  data_quality: dict[str, Any], snapshot_at: str,
                  catalyst_state: dict[str, Any] | None = None) -> dict[str, Any]:
    row = {
        "underlying_id": underlying_id, "strategy_type": c.strategy, "direction": c.direction,
        "direction_source": direction_source, "expiry": c.expiry.isoformat(), "legs": c.legs, "qty": c.qty,
        "entry_debit": c.entry_debit, "mid_debit": c.mid_debit, "max_loss_contract": c.max_loss_contract,
        "max_loss_total": c.max_loss_total, "max_profit_contract": c.max_profit_contract,
        "breakeven": c.breakeven, "costs_contract": c.costs_contract, "exec_overcost_pct": c.exec_overcost_pct,
        "exit_plan": c.exit_plan, "eligibility_status": "pending", "rejection_reasons": [],
        "warnings": c.warnings, "data_quality": data_quality, "model_version": MODEL_VERSION,
        "settings_version": settings_version, "snapshot_at": snapshot_at,
    }
    if catalyst_state is not None:
        if row.get("exit_plan") is None:
            row["exit_plan"] = {}
        row["exit_plan"]["catalyst_state"] = catalyst_state
    return row


def generate_for_underlying(sb, und: dict[str, Any], eff: dict[str, Any], settings_version: int = 0) -> dict[str, Any]:
    """Regenera las candidatas 'pending'/'rejected' del subyacente a partir de los datos guardados."""
    uid = und["id"]
    price = float(und["price"]) if und.get("price") is not None else None
    contracts = (sb.table("opt_contracts").select("*, opt_quotes_latest(*)").eq("underlying_id", uid)
                 .eq("active", True).execute().data or [])
    # reemplazo idempotente: se borran pending/rejected/eligible (nunca 'selected')
    sb.table("opt_candidates").delete().eq("underlying_id", uid).in_("eligibility_status", ["pending", "rejected", "eligible"]).execute()

    if not und.get("optionable") or price is None or not contracts:
        return {"symbol": und["symbol"], "candidates": 0, "rejected": 0, "skipped": "no optionable / sin precio / sin contratos"}

    quotes = [_to_quote(c) for c in contracts]
    raw_dir = und.get("direction")
    norm_dir = "bullish" if raw_dir in ("CALL", "bullish") else ("bearish" if raw_dir in ("PUT", "bearish") else None)
    directions = (norm_dir,) if norm_dir else ("bullish", "bearish")
    dir_source = und.get("direction_source") or ("apex" if norm_dir else "unverified")
    valid, rejected = st.generate(quotes, price, datetime.now(timezone.utc).date(), eff, directions, symbol=und.get("symbol", ""))

    states = Counter(q.market_data_type or "UNKNOWN" for q in quotes)
    dq = {"quote_states": dict(states), "usable_quotes": sum(1 for q in quotes if q.usable), "total_quotes": len(quotes)}
    now = datetime.now(timezone.utc).isoformat()
    ALLOWED_DB_STRATEGIES = {"long_call", "long_put", "bull_call_spread", "bear_put_spread"}
    rows = [candidate_row(c, uid, dir_source, settings_version, dq, now, catalyst_state=und.get("catalyst_state"))
            for c in valid if c.strategy in ALLOWED_DB_STRATEGIES]

    reasons_count: Counter = Counter()
    for r in rejected:
        for why in r["reasons"]:
            reasons_count[why.split(":")[0] if "dato no disponible" in why else why] += 1
    rej_rows = []
    for r in rejected[:MAX_REJECTED_SAMPLE]:
        strat = r["strategy"]
        if strat not in ALLOWED_DB_STRATEGIES:
            continue
        rej_rows.append({
            "underlying_id": uid, "strategy_type": strat, "direction": st.STRATEGY_DIRECTION[strat],
            "direction_source": dir_source, "expiry": r["expiry"],
            "legs": [{"desc": d} for d in r["legs"]], "eligibility_status": "rejected",
            "rejection_reasons": r["reasons"], "data_quality": dq, "model_version": MODEL_VERSION,
            "settings_version": settings_version, "snapshot_at": now,
        })
    if rows:
        sb.table("opt_candidates").insert(rows).execute()
    if rej_rows:
        sb.table("opt_candidates").insert(rej_rows).execute()
    valued = value_underlying_candidates(sb, und, eff, settings_version) if rows else {"eligible": 0, "val_rejected": 0}
    return {"symbol": und["symbol"], "candidates": len(rows), "rejected": len(rejected), **valued,
            "top_rejection_reasons": reasons_count.most_common(5)}


def generate_all(sb, eff: dict[str, Any], settings_version: int = 0) -> dict[str, Any]:
    unds = sb.table("opt_underlyings").select("*").eq("optionable", True).execute().data or []
    out = [generate_for_underlying(sb, u, eff, settings_version) for u in unds]
    total = sum(o["candidates"] for o in out)
    log_info(MODULE, f"Candidatas: {total} en {len(out)} subyacentes optionables")
    portfolio_res = run_portfolio_selection(sb, eff, settings_version)
    return {"underlyings": len(out), "candidates": total, "details": out, "portfolio_selection": portfolio_res}


def payoff_curve(row: dict[str, Any], points: int = 41) -> list[dict[str, float]]:
    """P&L neto al vencimiento por contrato (qty=1), calculado en backend a partir de las piernas guardadas."""
    legs = row.get("legs") or []
    if not legs or row.get("entry_debit") is None or row.get("costs_contract") is None or not all("strike" in l for l in legs):
        return []
    strikes = [float(l["strike"]) for l in legs]
    lo, hi = min(strikes) * 0.85, max(strikes) * 1.15
    debit, costs = float(row["entry_debit"]), float(row["costs_contract"])
    out = []
    for i in range(points):
        s = lo + (hi - lo) * i / (points - 1)
        value = sum((1 if l["side"] == "buy" else -1) * st.intrinsic(l["right"], float(l["strike"]), s) for l in legs)
        out.append({"price": round(s, 4), "pnl": round((value - debit) * 100 - costs, 2)})
    return out


def _event_flags(und: dict[str, Any]) -> list[str] | None:
    """None = no verificado (el scanner aun no integra earnings/catalizadores)."""
    if any("no verificado" in w for w in (und.get("warnings") or [])):
        return None
    return list(und.get("event_flags") or [])


def value_underlying_candidates(sb, und: dict[str, Any], eff: dict[str, Any], settings_version: int = 0) -> dict[str, int]:
    """Sprint 4 y 5: valora (EV neutral/APEX, escenarios), pasa por ADUANA, calcula Options Score y fija elegibilidad."""
    uid, price = und["id"], float(und["price"])
    rows = sb.table("opt_candidates").select("*").eq("underlying_id", uid).eq("eligibility_status", "pending").execute().data or []
    today = datetime.now(timezone.utc).date()
    n_ok = n_bad = 0
    for row in rows:
        val = val_.value_candidate(row, price, eff, today, direction_verified=(row.get("direction_source") in ("apex", "catalyst")))
        ad = aduana.validate_entry(row, aduana.static_context(uid, _event_flags(und), underlying=und), eff)
        ev_ok, ev_reasons = val_.eligibility_from_valuation(val, eff)
        approved = ad.approved and ev_ok
        reasons = ad.reasons + ev_reasons

        # Sprint 5: calcular Options Score de la candidata
        cand_for_score = dict(row)
        if not val.get("error"):
            cand_for_score.update(
                ev_neutral_net=val["ev_neutral_net"], ev_view_net=val["ev_view_net"],
                pop_neutral=val["pop_neutral"], pop_view=val["pop_view"],
                alpha_used=val["alpha_used"], expected_move=val["expected_move"],
                ev_view_adverse=val["ev_view_adverse"], ev_ratio=val["ev_ratio"],
                worst_adverse_scenario_pnl=val.get("worst_adverse_scenario_pnl"),
            )
        score_res = sc.score_candidate(cand_for_score, und, eff)
        is_dead = score_res.get("score_breakdown", {}).get("is_dead_stock", False)
        if is_dead:
            approved = False
            dead_reason = score_res.get("score_breakdown", {}).get("dead_stock_shield_reason") or "dead_stock_shield"
            if dead_reason not in reasons:
                reasons.append(dead_reason)

        upd = {
            "eligibility_status": "eligible" if approved else "rejected",
            "rejection_reasons": reasons,
            "score": score_res["score"],
            "score_breakdown": score_res["score_breakdown"],
            "model_version": MODEL_VERSION,
            "settings_version": settings_version,
            "valuation_warnings": (val.get("warnings") or []) + ad.warnings,
        }
        if not val.get("error"):
            upd.update(ev_neutral_net=val["ev_neutral_net"], ev_view_net=val["ev_view_net"], pop_neutral=val["pop_neutral"],
                       pop_view=val["pop_view"], alpha_used=val["alpha_used"], expected_move=val["expected_move"],
                       ev_view_adverse=val["ev_view_adverse"], ev_ratio=val["ev_ratio"])
        sb.table("opt_candidates").update(upd).eq("id", row["id"]).execute()
        if not val.get("error"):
            sb.table("opt_simulations").insert({
                "candidate_id": row["id"],
                "scenario_config": {k: val[k] for k in ("horizon_hours", "sigma_h", "iv_ref", "alpha_used", "T0_years", "T_exit_years", "model")},
                "scenario_results": {"grid": val["scenarios"], "worst_adverse_pnl": val["worst_adverse_scenario_pnl"],
                                     "ev_neutral_adverse": val["ev_neutral_adverse"], "ev_view_adverse": val["ev_view_adverse"]},
                "cost_assumptions": {"costs_contract": row.get("costs_contract"),
                                     "slippage_normal": eff["slippage_normal"], "slippage_adverse": eff["slippage_adverse"],
                                     "exit_spread_mult_normal": eff["exit_spread_mult_normal"],
                                     "exit_spread_mult_adverse": eff["exit_spread_mult_adverse"]},
                "pricing_model_version": MODEL_VERSION,
            }).execute()
        sb.table("opt_aduana_decisions").insert({
            "candidate_id": row["id"], "kind": "valuation", "approved": approved,
            "rules": ad.to_dict()["rules"], "warnings": ad.warnings + (val.get("warnings") or []),
            "settings_version": settings_version, "model_version": MODEL_VERSION,
        }).execute()
        n_ok += approved
        n_bad += (not approved)
    return {"eligible": n_ok, "val_rejected": n_bad}


def score_and_select(candidates: list[dict[str, Any]],
                     underlyings_by_id: dict[int, dict[str, Any]],
                     positions: list[Any],
                     eff: dict[str, Any],
                     realized_pnl_today: float = 0.0,
                     unrealized_pnl_today: float = 0.0) -> tuple[list[dict[str, Any]], sel.SelectionResult]:
    """Clasifica, puntua, asigna rankings y ejecuta la seleccion de cartera greedy."""
    ranked = sc.rank_and_score_candidates(candidates, underlyings_by_id, eff)
    selection = sel.select_portfolio(ranked, positions, eff, realized_pnl_today, unrealized_pnl_today)
    return ranked, selection


def run_portfolio_selection(sb, eff: dict[str, Any], settings_version: int = 0) -> dict[str, Any]:
    """Carga candidatas elegibles, puntua con rankings, ejecuta selector y persiste en opt_selections."""
    today = datetime.now(timezone.utc).date()
    und_rows = sb.table("opt_underlyings").select("*").execute().data or []
    und_map = {u["id"]: u for u in und_rows}

    # Limpiar candidatas obsoletas de días anteriores o vencimiento hoy (0DTE)
    today_start_iso = f"{today.isoformat()}T00:00:00+00:00"
    try:
        sb.table("opt_candidates").update({"eligibility_status": "rejected"}).in_("eligibility_status", ["eligible", "selected", "pending"]).lt("created_at", today_start_iso).execute()
    except Exception:
        pass

    # Candidatas candidatas a seleccion (SOLO las creadas hoy y con vencimiento posterior a hoy)
    raw_candidates = (sb.table("opt_candidates").select("*")
                      .in_("eligibility_status", ["eligible", "selected"])
                      .gte("created_at", today_start_iso)
                      .execute().data or [])
    candidates = [c for c in raw_candidates if str(c.get("expiry") or "")[:10] > today.isoformat()]
    if not candidates:
        return {"selected": [], "total_risk_allocated": 0.0, "status": "no eligible candidates"}

    try:
        pos_rows = sb.table("opt_paper_trades").select("*").eq("status", "open").execute().data or []
    except Exception:
        pos_rows = []

    ranked, sel_res = score_and_select(candidates, und_map, pos_rows, eff)

    # Actualizar opt_candidates con ranks y status
    selected_ids = {c["id"] for c in sel_res.selected}
    for c in ranked:
        cid = c["id"]
        is_sel = cid in selected_ids
        upd = {
            "rank_global": c.get("rank_global"),
            "rank_strategy": c.get("rank_strategy"),
            "score": c.get("score"),
            "score_breakdown": c.get("score_breakdown"),
            "eligibility_status": "selected" if is_sel else "eligible",
        }
        if is_sel:
            matching = next(s for s in sel_res.selected if s["id"] == cid)
            upd["qty"] = matching["qty"]
            upd["max_loss_total"] = matching["max_loss_total"]
        sb.table("opt_candidates").update(upd).eq("id", cid).execute()

    # La ejecución hacia TWS se realiza exclusivamente en run_options_auto_execution_cycle con validación de slots del Broker.

    try:
        sb.table("opt_selections").insert({
            "session_date": today.isoformat(),
            "selected_candidate_ids": list(selected_ids),
            "selections_detail": sel_res.selected,
            "skipped_detail": sel_res.skipped,
            "total_risk_allocated": sel_res.total_risk_allocated,
            "remaining_budget": sel_res.remaining_budget,
            "portfolio_state": {
                "open_positions": len(pos_rows),
                "used_open_risk": sel_res.used_open_risk,
                "daily_stop_triggered": sel_res.daily_stop_triggered,
            },
            "model_version": MODEL_VERSION,
            "settings_version": settings_version,
        }).execute()
    except Exception as exc:
        log_info(MODULE, f"Aviso al guardar opt_selections: {exc}")

    return sel_res.to_dict()

