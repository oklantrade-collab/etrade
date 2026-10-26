"""API del modulo Options (PAPER ONLY). No habla con IBKR: lee/escribe Supabase.

El Options Worker local es el unico proceso con acceso a TWS.
"""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth_handler import check_role
from app.core.logger import log_info, log_warning
from app.core.supabase_client import get_supabase
from app.options import settings_defaults as sd
from app.options.strategies_catalog import (
    STRATEGY_CATALOG,
    calculate_generic_payoff,
    closed_formula_oracle,
    get_all_strategies,
    get_strategy_definition,
)

router = APIRouter()
ceo_only = Depends(check_role(["CEO"]))

HEARTBEAT_STALE_SEC = 120


def _load_stored() -> tuple[dict[str, Any], int, str | None]:
    """Devuelve (valores, version, error). Si la tabla no existe -> defaults."""
    try:
        rows = get_supabase().table("opt_settings").select("key,value,updated_at").execute().data or []
    except Exception as e:  # tabla no migrada aun
        return {}, 0, str(e)[:200]
    stored: dict[str, Any] = {}
    version = 0
    for r in rows:
        if r["key"] == "_version":
            version = int(r["value"])
        else:
            stored[r["key"]] = r["value"]
    return stored, version, None


@router.get("/status")
def status():
    caps = sd.hard_caps()
    worker, worker_err = None, None
    try:
        res = get_supabase().table("opt_worker_heartbeat").select("*").eq("worker", "options_worker").execute().data
        worker = res[0] if res else None
    except Exception as e:
        worker_err = str(e)[:200]

    worker_state = "OFFLINE"
    if worker and worker.get("updated_at"):
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(worker["updated_at"].replace("Z", "+00:00"))).total_seconds()
        worker_state = "ONLINE" if age <= HEARTBEAT_STALE_SEC else "STALE"

    raw_ds = (worker or {}).get("data_state") or "UNKNOWN"
    if raw_ds in ("ERROR", "UNKNOWN") and worker_state == "ONLINE":
        raw_ds = "LIVE"

    return {
        "module_enabled": sd.options_enabled(),
        "execution_mode": sd.EXECUTION_MODE,
        "execution_mode_ok": sd.execution_mode_ok(),
        "paper": True,
        "hard_caps": caps,
        "worker": {"state": worker_state, "data_state": raw_ds, "error": worker_err},
        "model_version": "v0-foundation",
    }


@router.get("/settings")
def get_settings():
    stored, version, err = _load_stored()
    return {
        "settings": {**sd.default_settings(), **stored},
        "effective": sd.effective_settings(stored),
        "defaults": sd.default_settings(),
        "ranges": {k: {"min": v[1], "max": v[2]} for k, v in sd.PARAMS.items()},
        "locked": sd.LOCKED,
        "hard_caps": sd.hard_caps(),
        "settings_version": version,
        "storage_error": err,
    }


@router.put("/settings")
def put_settings(payload: dict, user: dict = ceo_only):
    if not sd.execution_mode_ok():
        raise HTTPException(status_code=409, detail="OPTIONS_EXECUTION_MODE invalido: solo 'paper'")
    values = payload.get("values") or {}
    clean, errors = sd.validate_settings(values)
    stored, version, err = _load_stored()
    if err:
        raise HTTPException(status_code=503, detail="Tablas opt_* no disponibles. Ejecutar backend/sql/opt_001_foundation.sql")
    merged = {**sd.default_settings(), **stored, **clean}
    errors += sd.validate_cross_rules(merged)
    caps = sd.hard_caps()
    if merged["max_risk_per_trade_usd"] > caps["max_risk_per_trade_usd"]:
        errors.append(f"max_risk_per_trade_usd supera el techo del entorno ({caps['max_risk_per_trade_usd']})")
    if merged["max_open_risk_usd"] > caps["max_open_risk_usd"]:
        errors.append(f"max_open_risk_usd supera el techo del entorno ({caps['max_open_risk_usd']})")
    if merged["max_daily_selections"] > caps["max_daily_selections"]:
        errors.append(f"max_daily_selections supera el techo del entorno ({int(caps['max_daily_selections'])})")
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    sb = get_supabase()
    who = str((user or {}).get("email") or (user or {}).get("sub") or "unknown")
    new_version = version + 1
    changed = {k: v for k, v in clean.items() if merged.get(k) != {**sd.default_settings(), **stored}.get(k)}
    for k, v in clean.items():
        sb.table("opt_settings").upsert({"key": k, "value": v, "updated_by": who}).execute()
    for k, v in changed.items():
        old = {**sd.default_settings(), **stored}.get(k)
        sb.table("opt_settings_audit").insert({
            "settings_version": new_version, "key": k, "old_value": old, "new_value": v, "changed_by": who,
        }).execute()
    sb.table("opt_settings").upsert({"key": "_version", "value": new_version, "updated_by": who}).execute()
    log_info("OPTIONS", f"Settings Options v{new_version} actualizados por {who}: {list(changed)}")
    return {"ok": True, "settings_version": new_version, "changed": list(changed)}


@router.get("/settings/audit")
def settings_audit(limit: int = 50):
    try:
        data = get_supabase().table("opt_settings_audit").select("*").order("changed_at", desc=True).limit(min(limit, 200)).execute().data
    except Exception as e:
        log_warning("OPTIONS", f"audit no disponible: {e}")
        data = []
    return {"items": data}


@router.get("/g1")
def g1_progress():
    """Avance hacia el Gate G1 (Sprint 0.5) a partir de opt_g1_sessions."""
    stored, _, _ = _load_stored()
    eff = sd.effective_settings(stored)
    try:
        rows = get_supabase().table("opt_g1_sessions").select("*").order("session_date", desc=True).limit(60).execute().data or []
    except Exception:
        rows = []
    n = len(rows)
    passed = sum(1 for r in rows if r.get("session_pass"))
    pct = (passed / n * 100) if n else 0
    go = n >= eff["g1_min_sessions"] and pct >= eff["g1_pct_sessions"]
    return {
        "sessions_measured": n, "sessions_passed": passed, "pct_passed": round(pct, 1),
        "required_sessions": eff["g1_min_sessions"], "required_pct": eff["g1_pct_sessions"],
        "verdict": "GO" if go else ("PENDING" if n < eff["g1_min_sessions"] else "NO-GO"),
        "sessions": rows,
    }


# ---------------------------------------------------------------------------
# Sprint 2: universo, jobs y cadenas almacenadas (la API NO habla con IBKR)
# ---------------------------------------------------------------------------
@router.get("/universe")
def universe():
    try:
        rows = (get_supabase().table("opt_underlyings").select("*").order("optionable", desc=True)
                .order("apex_score", desc=True).limit(100).execute().data or [])
    except Exception as e:
        return {"items": [], "optionable": 0, "rejected": 0, "error": str(e)[:200]}
    opt = sum(1 for r in rows if r.get("optionable"))
    calls = [r for r in rows if (r.get("direction") or "").upper() in ("CALL", "BULLISH")]
    puts = [r for r in rows if (r.get("direction") or "").upper() in ("PUT", "BEARISH")]
    return {
        "items": rows,
        "optionable": opt,
        "rejected": len(rows) - opt,
        "calls_count": len(calls),
        "puts_count": len(puts),
    }


@router.post("/catalysts/scan")
def trigger_catalyst_scan(payload: dict | None = None, user: dict = ceo_only):
    """Ejecuta el escaneo y arbitraje de los 4 catalizadores (CALL/PUT) para el universo."""
    from app.options.catalysts.service import run_catalyst_scan
    sb = get_supabase()
    stored, _, _ = _load_stored()
    eff = sd.effective_settings(stored)
    custom_tickers = (payload or {}).get("symbols")
    res = run_catalyst_scan(sb, eff=eff, custom_tickers=custom_tickers)
    return res


@router.get("/catalysts/state")
def get_catalyst_state():
    """Devuelve el estado de catalizadores activo por simbolo."""
    from app.options.catalysts.service import get_latest_catalyst_cache
    cached = get_latest_catalyst_cache()
    try:
        rows = get_supabase().table("universe_catalyst_state").select("*").order("catalyst_score", desc=True).limit(100).execute().data or []
    except Exception:
        rows = list(cached.values()) if cached else []

    if not rows and cached:
        rows = list(cached.values())

    calls = [r for r in rows if (r.get("direction") or "").upper() in ("CALL", "BULLISH")]
    puts = [r for r in rows if (r.get("direction") or "").upper() in ("PUT", "BEARISH")]
    return {"items": rows, "calls": calls, "puts": puts, "total": len(rows)}


@router.get("/universe/pool")
def get_universe_pool(direction: str | None = None, limit: int = 100):
    """Devuelve los simbolos de universe_pool (Opciones y Stocks)."""
    sb = get_supabase()
    try:
        q = sb.table("universe_pool").select("*")
        if direction:
            q = q.eq("pool_type", direction)
        rows = q.order("updated_at", desc=True).limit(min(limit, 200)).execute().data or []
        if rows:
            return {"items": rows, "count": len(rows)}
    except Exception:
        pass

    try:
        q = sb.table("opt_underlyings").select("id,symbol,price,direction,apex_score,optionable,updated_at")
        if direction:
            q = q.eq("direction", direction)
        rows = q.order("optionable", desc=True).limit(min(limit, 200)).execute().data or []
        return {"items": rows, "count": len(rows)}
    except Exception as e:
        return {"items": [], "error": str(e)[:200]}


@router.post("/jobs/scan")
def create_scan_job(payload: dict | None = None, user: dict = ceo_only):
    if not sd.options_enabled():
        raise HTTPException(status_code=409, detail="OPTIONS_ENABLED=false")
    if not sd.execution_mode_ok():
        raise HTTPException(status_code=409, detail="OPTIONS_EXECUTION_MODE invalido: solo 'paper'")
    sb = get_supabase()
    pending = sb.table("opt_jobs").select("id").in_("status", ["pending", "running"]).eq("type", "scan").limit(1).execute().data
    if pending:
        raise HTTPException(status_code=409, detail=f"Ya hay un scan en curso (job {pending[0]['id']})")
    symbols = [str(s).upper() for s in ((payload or {}).get("symbols") or [])][:40]
    who = str((user or {}).get("email") or (user or {}).get("sub") or "unknown")
    job = sb.table("opt_jobs").insert({"type": "scan", "params": {"symbols": symbols or None}, "created_by": who}).execute().data[0]
    return {"job_id": job["id"], "status": job["status"]}


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    rows = get_supabase().table("opt_jobs").select("*").eq("id", job_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="job no encontrado")
    return rows[0]


@router.get("/jobs")
def list_jobs(limit: int = 10):
    try:
        return {"items": get_supabase().table("opt_jobs").select("*").order("created_at", desc=True).limit(min(limit, 50)).execute().data}
    except Exception:
        return {"items": []}


@router.get("/chains/{symbol}")
def stored_chain(symbol: str):
    """Cadena almacenada (ultimos datos guardados por el worker), con calidad de dato por contrato."""
    sb = get_supabase()
    und = sb.table("opt_underlyings").select("*").eq("symbol", symbol.upper()).execute().data
    if not und:
        raise HTTPException(status_code=404, detail="subyacente no encontrado en opt_underlyings")
    contracts = (sb.table("opt_contracts").select("*, opt_quotes_latest(*)").eq("underlying_id", und[0]["id"])
                 .eq("active", True).order("expiry").order("strike").execute().data or [])
    return {"underlying": und[0], "contracts": contracts}


# ---------------------------------------------------------------------------
# Sprint 3: candidatas
# ---------------------------------------------------------------------------
@router.post("/jobs/candidates")
def create_candidates_job(user: dict = ceo_only):
    """Regenera candidatas desde los datos guardados (no requiere TWS)."""
    sb = get_supabase()
    who = str((user or {}).get("email") or (user or {}).get("sub") or "unknown")
    job = sb.table("opt_jobs").insert({"type": "candidates", "params": {}, "created_by": who}).execute().data[0]
    return {"job_id": job["id"], "status": job["status"]}


CANDIDATE_SUMMARY_COLS = (
    "id,underlying_id,strategy_type,direction,direction_source,expiry,legs,qty,"
    "entry_debit,max_loss_total,max_profit_contract,breakeven,ev_view_net,ev_neutral_net,"
    "pop_view,pop_neutral,score,eligibility_status,rank_global,rank_strategy,created_at,"
    "exit_plan,score_breakdown,"
    "opt_underlyings(symbol,price,apex_score,data_state,direction)"
)


@router.get("/candidates")
def list_candidates(status: str = "pending", strategy: str | None = None, direction: str | None = None,
                    symbol: str | None = None, limit: int = 100):
    if status not in ("pending", "rejected", "eligible", "selected", "all"):  # noqa
        raise HTTPException(status_code=422, detail="status invalido")
    try:
        q = get_supabase().table("opt_candidates").select(CANDIDATE_SUMMARY_COLS)
        if status != "all":
            q = q.eq("eligibility_status", status)
        if strategy:
            q = q.eq("strategy_type", strategy)
        if direction:
            q = q.eq("direction", direction)
        items = q.order("created_at", desc=True).limit(min(limit, 300)).execute().data or []
    except Exception as e:
        return {"items": [], "error": str(e)[:200]}
    if symbol:
        items = [i for i in items if (i.get("opt_underlyings") or {}).get("symbol") == symbol.upper()]
    return {"items": items}


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: int):
    rows = get_supabase().table("opt_candidates").select("*, opt_underlyings(symbol,price,apex_score,data_state)").eq("id", candidate_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="candidata no encontrada")
    from app.options.candidates import payoff_curve
    sb = get_supabase()
    sim = sb.table("opt_simulations").select("scenario_config,scenario_results,cost_assumptions,pricing_model_version").eq("candidate_id", candidate_id).order("created_at", desc=True).limit(1).execute().data
    dec = sb.table("opt_aduana_decisions").select("kind,approved,rules,warnings,created_at").eq("candidate_id", candidate_id).order("created_at", desc=True).limit(1).execute().data
    row = rows[0]
    bd = row.get("score_breakdown") or {}
    st_reg = bd.get("structural_regime") or {}
    return {
        **row,
        "structural_regime": st_reg,
        "setup_name": bd.get("setup_name"),
        "setup_label": bd.get("setup_label"),
        "payoff": payoff_curve(row),
        "simulation": sim[0] if sim else None,
        "aduana": dec[0] if dec else None,
    }


# ---------------------------------------------------------------------------
# Sprint 5: Opportunities & Portfolio Selector
# ---------------------------------------------------------------------------
@router.get("/opportunities")
def list_opportunities(strategy: str | None = None, direction: str | None = None,
                       status: str = "all", symbol: str | None = None, min_score: float | None = None,
                       gap_runner_only: bool = False, gap_type: str | None = None,
                       limit: int = 100):
    """Vista consolidada de Opportunities con ranking, score, desglose y resumen de cartera."""
    sb = get_supabase()
    stored, version, _ = _load_stored()
    eff = sd.effective_settings(stored)
    try:
        q = sb.table("opt_candidates").select(CANDIDATE_SUMMARY_COLS)
        if status != "all":
            q = q.eq("eligibility_status", status)
        if strategy:
            q = q.eq("strategy_type", strategy)
        if direction:
            q = q.eq("direction", direction)
        if min_score is not None:
            q = q.gte("score", min_score)
        items = q.order("score", desc=True, nullsfirst=False).limit(min(limit, 300)).execute().data or []
        # Ordenar: Seleccionadas primero, luego Elegibles, luego Rechazadas; priorizando rank_global y score
        status_order = {"selected": 0, "eligible": 1, "rejected": 2}
        items.sort(key=lambda x: (
            status_order.get(x.get("eligibility_status"), 3),
            int(x.get("rank_global") or 99999),
            -float(x.get("score") or 0.0),
        ))
    except Exception as e:
        return {"items": [], "error": str(e)[:200]}

    from app.options.aduana_gap_runner_options import get_min_gap_threshold

    # Enriquecer candidatas con indicadores ADUANA GAP RUNNER
    for item in items:
        exit_plan = item.get("exit_plan") or {}
        score_bd = item.get("score_breakdown") or {}
        und = item.get("opt_underlyings") or {}
        sym = (und.get("symbol") or "").upper()

        is_runner = bool(
            exit_plan.get("is_gap_runner")
            or score_bd.get("is_gap_runner")
            or item.get("direction_source") == "gap_runner"
            or item.get("strategy_type") in ("gap_runner_call", "gap_runner_put")
        )
        g_type = exit_plan.get("gap_type") or score_bd.get("gap_type")
        g_pct = float(exit_plan.get("gap_pct") or score_bd.get("gap_pct") or 0.0)

        if not is_runner and sym:
            min_gap = get_min_gap_threshold(sym)
            c_dir = (item.get("direction") or "").lower()
            u_gap = float(und.get("gap_pct") or exit_plan.get("gap_pct") or 0.0)
            if c_dir in ("call", "bullish") and u_gap >= min_gap:
                is_runner = True
                g_type = "OPEN_GAP_UP"
                g_pct = u_gap
            elif c_dir in ("put", "bearish") and u_gap <= -min_gap:
                is_runner = True
                g_type = "OPEN_GAP_DOWN"
                g_pct = u_gap

        bd = item.get("score_breakdown") or {}
        item["is_gap_runner"] = is_runner
        item["gap_type"] = g_type
        item["gap_pct"] = g_pct
        item["catalyst_state"] = exit_plan.get("catalyst_state")
        item["structural_regime"] = bd.get("structural_regime") or {}
        item["setup_name"] = bd.get("setup_name")
        item["setup_label"] = bd.get("setup_label")

    if gap_runner_only:
        items = [i for i in items if i.get("is_gap_runner")]

    if gap_type:
        items = [i for i in items if (i.get("gap_type") or "").upper() == gap_type.upper()]

    if symbol:
        items = [i for i in items if (i.get("opt_underlyings") or {}).get("symbol") == symbol.upper()]

    total = len(items)
    selected = [i for i in items if i.get("eligibility_status") == "selected"]
    eligible = [i for i in items if i.get("eligibility_status") == "eligible"]
    rejected = [i for i in items if i.get("eligibility_status") == "rejected"]
    # FILTRO ESTRICTO: En el TOP RANKING de Opciones, SOLO candidatas potencialmente ELEGIBLES o SELECCIONADAS
    # Las descartadas por Aduana o reglas NUNCA deben mostrarse en el Top 3
    calls = [
        i for i in items
        if i.get("direction") in ("CALL", "bullish")
        and i.get("eligibility_status") in ("eligible", "selected")
        and float(i.get("score") or 0.0) > 0.0
        and not (i.get("score_breakdown") or {}).get("is_dead_stock", False)
    ]
    puts = [
        i for i in items
        if i.get("direction") in ("PUT", "bearish")
        and i.get("eligibility_status") in ("eligible", "selected")
        and float(i.get("score") or 0.0) > 0.0
        and not (i.get("score_breakdown") or {}).get("is_dead_stock", False)
    ]
    gap_runners = [i for i in items if i.get("is_gap_runner")]
    gap_up_runners = [i for i in gap_runners if i.get("gap_type") == "OPEN_GAP_UP"]
    gap_down_runners = [i for i in gap_runners if i.get("gap_type") == "OPEN_GAP_DOWN"]

    def _distinct_by_symbol(cands: list[dict], top_n: int = 3) -> list[dict]:
        out = []
        seen = set()
        sorted_cands = sorted(cands, key=lambda x: (
            0 if x.get("is_gap_runner") else 1,   # Prioridad a Gap Runners
            -float(x.get("score") or 0.0),
            -float(x.get("ev_ratio") or x.get("ev_view_net") or 0.0),
            -float(x.get("max_profit_contract") or 0.0)
        ))
        for c in sorted_cands:
            sym = (c.get("opt_underlyings") or {}).get("symbol") or "UNKNOWN"
            if sym not in seen:
                seen.add(sym)
                out.append(c)
                if len(out) >= top_n:
                    break
        return out

    top_calls = _distinct_by_symbol(calls, 3)
    top_puts = _distinct_by_symbol(puts, 3)

    # Considerar riesgo de seleccionadas y también de trades de opciones ya abiertos en opt_paper_trades
    try:
        open_opt_trades = sb.table("opt_paper_trades").select("max_loss_total").eq("status", "open").execute().data or []
        open_trades_risk = sum(float(p.get("max_loss_total") or 0.0) for p in open_opt_trades)
    except Exception:
        open_trades_risk = 0.0
    selected_risk = sum(float(s.get("max_loss_total") or 0.0) for s in selected)
    allocated_risk = open_trades_risk + selected_risk
    max_open_risk = float(eff.get("max_open_risk_usd") or 100.0)
    remaining_budget = max(0.0, max_open_risk - allocated_risk)

    return {
        "items": items,
        "summary": {
            "total_candidates": total,
            "total_calls": len(calls),
            "total_puts": len(puts),
            "total_gap_runners": len(gap_runners),
            "total_gap_up": len(gap_up_runners),
            "total_gap_down": len(gap_down_runners),
            "has_gap_runners": len(gap_runners) > 0,
            "top_calls": top_calls,
            "top_puts": top_puts,
            "selected_count": len(selected),
            "eligible_count": len(eligible),
            "rejected_count": len(rejected),
            "allocated_risk_usd": round(allocated_risk, 2),
            "max_open_risk_usd": max_open_risk,
            "remaining_budget_usd": round(remaining_budget, 2),
            "min_score_setting": eff.get("min_score", 60),
            "max_candidates_per_direction": eff.get("max_candidates_per_direction", 25),
        },
    }


@router.post("/portfolio/select")
def trigger_portfolio_selection(user: dict = ceo_only):
    """Ejecuta el selector de cartera con las candidatas y configuraciones vigentes."""
    from app.options.candidates import run_portfolio_selection
    sb = get_supabase()
    stored, version, _ = _load_stored()
    eff = sd.effective_settings(stored)
    result = run_portfolio_selection(sb, eff, version)
    return {"ok": True, "result": result}


@router.get("/portfolio/selections")
def get_portfolio_selections(limit: int = 10):
    """Historial de ejecuciones del selector de cartera."""
    try:
        data = get_supabase().table("opt_selections").select("*").order("created_at", desc=True).limit(min(limit, 50)).execute().data or []
    except Exception as e:
        return {"items": [], "error": str(e)[:200]}
    return {"items": data}


# ---------------------------------------------------------------------------
# Sprint 6: Paper Trading Positions & Salidas
# ---------------------------------------------------------------------------
@router.get("/positions")
def list_positions(status: str = "open", symbol: str | None = None, strategy: str | None = None, limit: int = 100):
    """Lista posiciones de Paper Trading (abiertas y/o cerradas) con metricas agregadas."""
    sb = get_supabase()
    stored, _, _ = _load_stored()
    eff = sd.effective_settings(stored)
    try:
        q = sb.table("opt_paper_trades").select("*")
        if status != "all":
            q = q.eq("status", status)
        if symbol:
            q = q.eq("symbol", symbol.upper())
        if strategy:
            q = q.eq("strategy_type", strategy)
        items = q.order("entry_time", desc=True).limit(min(limit, 300)).execute().data or []
    except Exception as e:
        return {"items": [], "error": str(e)[:200]}

    try:
        all_rows = sb.table("opt_paper_trades").select("status,unrealized_pnl,realized_pnl,max_loss_total").limit(500).execute().data or []
        open_pos = [p for p in all_rows if p.get("status") == "open"]
        closed_pos = [p for p in all_rows if p.get("status") == "closed"]
    except Exception:
        open_pos = [p for p in items if p.get("status") == "open"]
        closed_pos = [p for p in items if p.get("status") == "closed"]

    unrealized_total = sum(float(p.get("unrealized_pnl") or 0.0) for p in open_pos)
    realized_total = sum(float(p.get("realized_pnl") or 0.0) for p in closed_pos)
    open_risk = sum(float(p.get("max_loss_total") or 0.0) for p in open_pos)
    winning_trades = sum(1 for p in closed_pos if float(p.get("realized_pnl") or 0.0) > 0)
    win_rate = (winning_trades / len(closed_pos) * 100.0) if closed_pos else 0.0

    return {
        "items": items,
        "summary": {
            "open_positions": len(open_pos),
            "closed_positions": len(closed_pos),
            "unrealized_pnl_usd": round(unrealized_total, 2),
            "realized_pnl_usd": round(realized_total, 2),
            "open_risk_usd": round(open_risk, 2),
            "max_open_risk_usd": float(eff.get("max_open_risk_usd") or 100.0),
            "win_rate_pct": round(win_rate, 1),
        },
    }


@router.get("/positions/{position_id}")
def get_position(position_id: int):
    """Detalle completo de una posicion paper con eventos de riesgo asociados."""
    sb = get_supabase()
    rows = sb.table("opt_paper_trades").select("*").eq("id", position_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Posicion no encontrada")
    pos = rows[0]
    events = sb.table("opt_risk_events").select("*").eq("paper_trade_id", position_id).order("created_at", desc=True).execute().data or []
    return {**pos, "risk_events": events}


@router.post("/positions/simulate-entry")
def simulate_entry(payload: dict, user: dict = ceo_only):
    """Simula la entrada de una candidata a Paper Trading tras aprobacion ADUANA."""
    if not sd.options_enabled():
        raise HTTPException(status_code=409, detail="OPTIONS_ENABLED=false")
    if not sd.execution_mode_ok():
        raise HTTPException(status_code=409, detail="OPTIONS_EXECUTION_MODE invalido: solo 'paper'")

    candidate_id = payload.get("candidate_id")
    if not candidate_id:
        raise HTTPException(status_code=422, detail="candidate_id requerido")

    sb = get_supabase()
    stored, version, _ = _load_stored()
    eff = sd.effective_settings(stored)

    cands = sb.table("opt_candidates").select("*, opt_underlyings(*)").eq("id", candidate_id).execute().data
    if not cands:
        raise HTTPException(status_code=404, detail="Candidata no encontrada")
    cand = cands[0]
    und = cand.get("opt_underlyings") or {}

    from app.options import options_aduana as aduana
    from app.options import paper_execution as pe

    now_dt = datetime.now(timezone.utc)
    event_flags = und.get("event_flags")
    ctx = aduana.static_context(cand["underlying_id"], event_flags)
    ctx.now = now_dt
    aduana_res = aduana.validate_entry(cand, ctx, eff)
    if not aduana_res.approved:
        raise HTTPException(status_code=422, detail=f"ADUANA rechazo la entrada: {aduana_res.reasons}")

    # ── VALIDACIÓN MACRO SENTIMENT (Propuesta #1) ──
    from app.core.macro_sentiment_engine import evaluate_macro_sentiment
    macro_sent = evaluate_macro_sentiment()
    direction_str = str(cand.get("direction") or "bullish").lower()
    strat_str = str(cand.get("strategy_type") or "").lower()
    is_call_strat = direction_str == "bullish" or "call" in strat_str
    if is_call_strat and not macro_sent.get("allow_option_calls", True):
        raise HTTPException(
            status_code=422,
            detail=f"Macro Sentiment Shield: Mercado en {macro_sent.get('regime')} ({macro_sent.get('label')}) prohíbe compras CALL y Bull Spreads. Foco institucional en Puts."
        )

    # ── VALIDACIÓN PRE-TRADE BID/ASK & LIQUIDEZ (Propuesta #2) ──
    from app.options.pre_trade_validator import validate_option_candidate_pre_trade
    legs_to_check = cand.get("legs") or []
    sym_und = und.get("symbol") or cand.get("symbol") or "UNKNOWN"
    exp_cand = cand.get("expiry") or "20261026"
    pre_eval = validate_option_candidate_pre_trade(
        symbol=sym_und,
        strategy_type=cand.get("strategy_type", "long_call"),
        expiry_yyyymmdd=exp_cand,
        legs=legs_to_check
    )
    if not pre_eval.get("is_valid", True):
        reasons_text = "; ".join(pre_eval.get("reasons", []))
        log_warning("OPTIONS_API", f"Pre-Trade Validator rechazo entrada en {sym_und}: {reasons_text}")
        raise HTTPException(
            status_code=422,
            detail=f"Rechazado por Pre-Trade Validator (Liquidez/Spread): {reasons_text}"
        )

    fill_res = pe.simulate_entry_fill(cand, None, eff, now_dt)

    pos_data = {
        "candidate_id": cand["id"],
        "underlying_id": cand["underlying_id"],
        "symbol": und.get("symbol") or "UNKNOWN",
        "strategy_type": cand["strategy_type"],
        "direction": cand["direction"],
        "status": "open",
        "qty": cand.get("qty") or 1,
        "expiry": cand["expiry"],
        "entry_time": fill_res.entry_time,
        "entry_debit": fill_res.entry_debit,
        "entry_fills": fill_res.entry_fills,
        "entry_costs": fill_res.entry_costs,
        "entry_total_invested": fill_res.entry_total_invested,
        "max_loss_total": float(cand.get("max_loss_total") or fill_res.entry_total_invested),
        "max_profit_total": (float(cand["max_profit_contract"]) * (cand.get("qty") or 1)) if cand.get("max_profit_contract") else None,
        "breakeven": cand.get("breakeven"),
        "unrealized_pnl": 0.0,
        "last_mark_price": fill_res.entry_debit,
        "last_mark_at": fill_res.entry_time,
        "exit_plan": cand.get("exit_plan") or {},
        "model_version": pe.MODEL_VERSION,
        "settings_version": version,
    }
    inserted = sb.table("opt_paper_trades").insert(pos_data).execute().data[0]
    sb.table("opt_candidates").update({"eligibility_status": "selected"}).eq("id", cand["id"]).execute()

    # Despachar legs a stocks_orders para ejecución por ib_bridge_worker (TWS)
    sym = und.get("symbol") or "UNKNOWN"
    exp_compact = (cand.get("expiry") or "20261026").replace("-", "")[:8]
    qty = cand.get("qty") or 1
    for f in fill_res.entry_fills:
        stk = f.get("strike")
        rgt = f.get("right")
        side = f.get("side") or "buy"
        px = float(f.get("fill_price") or f.get("mid") or f.get("ask") or 0.0)
        leg_lmt = px
        for leg_ev in pre_eval.get("legs", []):
            if float(leg_ev.get("strike") or 0) == float(stk or 0) and str(leg_ev.get("right") or "").upper() == str(rgt or "").upper():
                leg_lmt = float(leg_ev.get("mid") or px)
                break

        opt_target_band = f"OPT:{exp_compact}:{stk}:{rgt}"
        try:
            sb.table("stocks_orders").insert({
                "ticker": sym[:10],
                "target_band": opt_target_band,
                "group_name": "OPTIONS_AUTONOMOUS",
                "rule_code": "APEX_AUTO",
                "order_type": "limit",
                "limit_price": round(leg_lmt, 2),
                "direction": side,
                "shares": qty,
                "market_price": round(leg_lmt, 2),
                "status": "pending",
                "created_at": fill_res.entry_time,
            }).execute()
        except Exception:
            pass

    return {"ok": True, "position": inserted}


@router.post("/positions/{position_id}/simulate-exit")
def simulate_exit(position_id: int, payload: dict | None = None, user: dict = ceo_only):
    """Cierra la posición de opciones, transmite la orden de cierre al broker si aplica, y calcula el P&L con cotizaciones de mercado reales."""
    sb = get_supabase()
    stored, _, _ = _load_stored()
    eff = sd.effective_settings(stored)

    rows = sb.table("opt_paper_trades").select("*").eq("id", position_id).execute().data
    if not rows:
        raise HTTPException(status_code=404, detail="Posicion no encontrada")
    pos = rows[0]
    if pos["status"] != "open":
        raise HTTPException(status_code=409, detail=f"Posicion ya esta {pos['status']}")

    reason = (payload or {}).get("reason") or "manual_simulated"
    from app.options import paper_execution as pe

    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.isoformat()

    # 1. Obtener cotizaciones de mercado para todas las patas del contrato
    quotes_by_contract = {}
    entry_fills = pos.get("entry_fills") or []
    for ef in entry_fills:
        cid = ef.get("contract_id")
        conid = ef.get("conid")
        q_row = None
        if cid:
            try:
                res_q = sb.table("opt_quotes_latest").select("*").eq("contract_id", cid).limit(1).execute()
                if res_q.data and (res_q.data[0].get("bid") or res_q.data[0].get("last")):
                    q_row = res_q.data[0]
            except Exception:
                pass
        if not q_row and conid:
            try:
                c_res = sb.table("opt_contracts").select("id").eq("conid", conid).limit(1).execute()
                if c_res.data:
                    res_q = sb.table("opt_quotes_latest").select("*").eq("contract_id", c_res.data[0]["id"]).limit(1).execute()
                    if res_q.data and (res_q.data[0].get("bid") or res_q.data[0].get("last")):
                        q_row = res_q.data[0]
            except Exception:
                pass

        if q_row:
            if conid:
                quotes_by_contract[conid] = q_row
            if cid:
                quotes_by_contract[cid] = q_row
        elif pos.get("last_mark_price") and float(pos.get("last_mark_price") or 0) > 0:
            # Fallback al último mark_price visto (en vez del entry_debit)
            mark_p = float(pos.get("last_mark_price"))
            fake_q = {"bid": mark_p, "ask": mark_p, "last": mark_p, "market_data_type": "LAST_MARK"}
            if conid:
                quotes_by_contract[conid] = fake_q
            if cid:
                quotes_by_contract[cid] = fake_q

    # 2. Transmitir orden de cierre al broker (vía stocks_orders para que el bridge local de APOLO la envíe a TWS)
    sym = pos.get("symbol", "").upper()
    qty = int(pos.get("qty") or 1)
    exp = str(pos.get("expiry", "")).replace("-", "")
    strike = None
    right = "C" if pos.get("strategy_type", "").lower() == "long_call" else "P"
    if entry_fills:
        strike = entry_fills[0].get("strike")
        right = entry_fills[0].get("right") or right

    if sym and strike:
        try:
            mark_or_exit_px = float(pos.get("last_mark_price") or 0.0)
            target_band = f"OPT:{exp}:{strike}:{right}"
            sb.table("stocks_orders").insert({
                "ticker": sym,
                "group_name": "OPTIONS",
                "rule_code": "OPT_CALL" if right == "C" else "APEX_AUTO",
                "direction": "sell",
                "order_type": "limit" if mark_or_exit_px > 0 else "market",
                "limit_price": round(mark_or_exit_px, 2) if mark_or_exit_px > 0 else None,
                "market_price": round(mark_or_exit_px, 2) if mark_or_exit_px > 0 else None,
                "shares": qty,
                "target_band": target_band,
                "status": "pending",
                "created_at": now_iso
            }).execute()
            log_info("options_api", f"Orden SELL de cierre para opción {sym} {target_band} encolada para TWS en stocks_orders")
        except Exception as o_err:
            log_warning("options_api", f"Aviso al encolar orden de cierre en stocks_orders: {o_err}")

    # 3. Calcular salida con cotizaciones de mercado
    exit_fill = pe.simulate_exit_fill(pos, quotes_by_contract, eff, reason, adverse=False, now=now_dt)

    realized_val = exit_fill.realized_pnl
    # Asegurar que exit_reason sea válido según el constraint opt_paper_trades_exit_reason_check
    db_reason = "take_profit" if realized_val >= 0 else "stop_loss"
    if reason in ["take_profit", "stop_loss", "manual_simulated", "forced_close_time", "signal_invalidation", "bad_data_close"]:
        db_reason = reason

    upd = {
        "status": "closed",
        "exit_time": exit_fill.exit_time,
        "exit_credit": exit_fill.exit_credit,
        "exit_fills": exit_fill.exit_fills,
        "exit_costs": exit_fill.exit_costs,
        "exit_total_recovered": exit_fill.exit_total_recovered,
        "realized_pnl": exit_fill.realized_pnl,
        "unrealized_pnl": 0.0,
        "last_mark_price": exit_fill.exit_credit,
        "last_mark_at": now_dt.isoformat(),
        "exit_reason": db_reason,
        "updated_at": now_dt.isoformat(),
    }
    sb.table("opt_paper_trades").update(upd).eq("id", position_id).execute()

    return {"ok": True, "realized_pnl": exit_fill.realized_pnl, "position": {**pos, **upd}}


@router.post("/positions/evaluate-exits")
def evaluate_exits(user: dict = ceo_only):
    """Ejecuta el motor de salidas sobre todas las posiciones paper abiertas."""
    from app.options.exit_engine import process_open_positions
    sb = get_supabase()
    stored, _, _ = _load_stored()
    eff = sd.effective_settings(stored)
    result = process_open_positions(sb, eff)
    return {"ok": True, "result": result}


@router.delete("/positions/{position_id}")
def delete_position(position_id: int):
    """Elimina permanentemente una posición de opciones (opt_paper_trades)."""
    sb = get_supabase()
    res = sb.table("opt_paper_trades").delete().eq("id", position_id).execute()
    return {"ok": True, "deleted_id": position_id}


# ---------------------------------------------------------------------------
# Sprint 7: Performance, Calibración & Gate G3
# ---------------------------------------------------------------------------
@router.get("/performance/summary")
def get_performance_summary():
    """Resumen consolidado de metricas de rentabilidad, riesgo y curva de equidad."""
    sb = get_supabase()
    try:
        closed_trades = sb.table("opt_paper_trades").select("*").eq("status", "closed").execute().data or []
        open_trades = sb.table("opt_paper_trades").select("*").eq("status", "open").execute().data or []
    except Exception as e:
        return {"error": str(e)[:200]}

    from app.options.performance import calculate_performance
    res = calculate_performance(closed_trades, open_trades)
    return res


@router.get("/performance/calibration")
def get_performance_calibration(n_bins: int = 5):
    """Diagrama de calibracion de probabilidad teorica vs observada y estimacion de alpha."""
    sb = get_supabase()
    stored, _, _ = _load_stored()
    eff = sd.effective_settings(stored)
    try:
        trades = sb.table("opt_paper_trades").select("*, opt_candidates(pop_view,pop_neutral,ev_view_net,alpha_used)").eq("status", "closed").execute().data or []
    except Exception as e:
        return {"error": str(e)[:200]}

    from app.options.calibration import compute_binned_calibration, estimate_empirical_alpha
    binned = compute_binned_calibration(trades, n_bins=n_bins)
    alpha_est = estimate_empirical_alpha(trades, prior_alpha=float(eff.get("alpha") or 0.25))
    return {"calibration": binned, "alpha_estimation": alpha_est}


@router.get("/g3")
def get_gate_g3_status():
    """Evaluacion formal del Gate G3 (duracion shadow, volumen de operaciones, calibracion, expectancy)."""
    sb = get_supabase()
    stored, version, _ = _load_stored()
    eff = sd.effective_settings(stored)
    try:
        trades = sb.table("opt_paper_trades").select("*, opt_candidates(pop_view,pop_neutral,ev_view_net,alpha_used)").eq("status", "closed").execute().data or []
    except Exception as e:
        trades = []

    from app.options.g3_probe import evaluate_gate_g3
    eval_res = evaluate_gate_g3(trades, eff)

    try:
        sb.table("opt_g3_evaluations").insert({
            "evaluation_date": datetime.now(timezone.utc).date().isoformat(),
            "verdict": eval_res["verdict"],
            "total_trades": eval_res["summary"]["trades_count"],
            "weeks_in_shadow": eval_res["summary"]["weeks_in_shadow"],
            "expectancy_usd": eval_res["summary"]["expectancy_usd"],
            "win_rate_pct": eval_res["summary"]["win_rate_pct"],
            "max_drawdown_usd": eval_res["summary"]["max_drawdown_usd"],
            "calibration_error_pts": eval_res["summary"]["max_calibration_error_pts"],
            "criteria": eval_res["criteria"],
            "model_version": eval_res["model_version"],
            "settings_version": version,
        }).execute()
    except Exception:
        pass

    return eval_res


# ---------------------------------------------------------------------------
# Mantenimiento y Protección de Cuota Supabase Free Tier (Egress & Storage)
# ---------------------------------------------------------------------------
@router.post("/maintenance/cleanup")
def run_db_cleanup(payload: dict | None = None, user: dict = ceo_only):
    """Ejecuta purga de retencion de datos en Supabase (snapshots antiguos y candidatas descartadas)."""
    from datetime import timedelta
    sb = get_supabase()
    payload = payload or {}
    snap_days = int(payload.get("snapshots_days", 7))
    cand_days = int(payload.get("candidates_days", 3))

    # 1. Intentar via RPC almacenado en Postgres (opt_008)
    try:
        rpc_res = sb.rpc("cleanup_options_data", {
            "p_snapshots_days": snap_days,
            "p_candidates_days": cand_days,
            "p_jobs_days": 14,
        }).execute()
        if rpc_res.data:
            return {"ok": True, "method": "postgres_rpc", "result": rpc_res.data}
    except Exception as e:
        log_warning("OPTIONS_CLEANUP", f"RPC no disponible, ejecutando fallback Python: {e}")

    # 2. Fallback directo via API PostgREST
    now = datetime.now(timezone.utc)
    snap_cutoff = (now - timedelta(days=snap_days)).isoformat()
    cand_cutoff = (now - timedelta(days=cand_days)).isoformat()

    stats = {"deleted_snapshots": 0, "deleted_candidates": 0, "deleted_jobs": 0}
    try:
        snaps = sb.table("opt_snapshots").delete().lt("captured_at", snap_cutoff).execute()
        stats["deleted_snapshots"] = len(snaps.data or [])
    except Exception as e:
        stats["snapshots_error"] = str(e)[:150]

    try:
        cands = (sb.table("opt_candidates").delete()
                 .in_("eligibility_status", ["rejected", "expired"])
                 .lt("created_at", cand_cutoff).execute())
        stats["deleted_candidates"] = len(cands.data or [])
    except Exception as e:
        stats["candidates_error"] = str(e)[:150]

    try:
        jobs = (sb.table("opt_jobs").delete()
                .in_("status", ["done", "error"])
                .lt("created_at", (now - timedelta(days=14)).isoformat()).execute())
        stats["deleted_jobs"] = len(jobs.data or [])
    except Exception as e:
        stats["jobs_error"] = str(e)[:150]

    log_info("OPTIONS_CLEANUP", f"Limpieza completada: {stats}")
    return {"ok": True, "method": "python_fallback", "result": stats}


@router.get("/maintenance/db-stats")
def get_options_db_stats(user: dict = ceo_only):
    """Estadisticas de almacenamiento y conteo de filas en las tablas opt_* de Supabase."""
    sb = get_supabase()
    tables = [
        "opt_snapshots", "opt_quotes_latest", "opt_contracts", "opt_underlyings",
        "opt_candidates", "opt_simulations", "opt_aduana_decisions",
        "opt_paper_trades", "opt_risk_events", "opt_selections",
        "opt_g1_sessions", "opt_g3_evaluations", "opt_settings", "opt_settings_audit"
    ]
    counts: dict[str, int | str] = {}
    for tbl in tables:
        try:
            res = sb.table(tbl).select("id", count="exact").limit(1).execute()
            counts[tbl] = res.count if res.count is not None else len(res.data or [])
        except Exception:
            try:
                # Tablas sin columna 'id' (como opt_quotes_latest con contract_id o opt_settings con key)
                res = sb.table(tbl).select("*", count="exact").limit(1).execute()
                counts[tbl] = res.count if res.count is not None else len(res.data or [])
            except Exception as e:
                counts[tbl] = f"Error: {str(e)[:50]}"

    # Estimacion aproximada de almacenamiento
    est_bytes = (
        (counts.get("opt_snapshots", 0) if isinstance(counts.get("opt_snapshots"), int) else 0) * 250 +
        (counts.get("opt_candidates", 0) if isinstance(counts.get("opt_candidates"), int) else 0) * 1200 +
        (counts.get("opt_simulations", 0) if isinstance(counts.get("opt_simulations"), int) else 0) * 3500 +
        (counts.get("opt_quotes_latest", 0) if isinstance(counts.get("opt_quotes_latest"), int) else 0) * 300 +
        (counts.get("opt_contracts", 0) if isinstance(counts.get("opt_contracts"), int) else 0) * 200 +
        (counts.get("opt_paper_trades", 0) if isinstance(counts.get("opt_paper_trades"), int) else 0) * 1000
    )
    est_mb = round(est_bytes / (1024 * 1024), 2)

    return {
        "counts": counts,
        "estimated_module_mb": est_mb,
        "supabase_free_quota_mb": 500.0,
        "pct_of_free_quota": round((est_mb / 500.0) * 100, 2),
        "egress_optimizations_active": True,
        "snapshot_retention_days": 7,
        "candidate_retention_days": 3,
    }


@router.get("/strategies")
def list_strategies():
    """Catálogo maestro de las 14 estrategias de opciones con estado, familia y viabilidad económica."""
    return {
        "strategies": get_all_strategies(),
        "families": ["single-leg", "vertical", "multi-leg defined-risk", "calendar/diagonal"],
        "viable_for_capital_50": [k for k, v in STRATEGY_CATALOG.items() if v.capital_viable],
    }


@router.get("/strategies/{key}")
def get_strategy(key: str):
    """Detalle de una estrategia del catálogo."""
    strat = get_strategy_definition(key)
    if not strat:
        raise HTTPException(status_code=404, detail=f"Estrategia '{key}' no encontrada en el catálogo")
    return strat.__dict__


@router.post("/strategies/evaluate")
def evaluate_strategy_custom(payload: dict):
    """Evalúa payoff analítico y genérico para una configuración de patas personalizada (Addendum §11.2)."""
    legs = payload.get("legs") or []
    if not legs:
        raise HTTPException(status_code=400, detail="Se requiere al menos una pata ('legs')")

    strategy_key = payload.get("strategy_key") or "custom"
    underlying_price = float(payload.get("underlying_price") or 100.0)
    costs = float(payload.get("costs_total") or 0.0)
    multiplier = int(payload.get("multiplier") or 100)

    # Rango de precios para simular vencimiento (+/- 20%)
    price_min = float(payload.get("price_min") or max(underlying_price * 0.8, 0.01))
    price_max = float(payload.get("price_max") or underlying_price * 1.2)
    steps = int(payload.get("steps") or 41)

    step_size = (price_max - price_min) / max(steps - 1, 1)
    s_mesh = [round(price_min + i * step_size, 4) for i in range(steps)]

    payoff_curve = calculate_generic_payoff(legs, entry_net_per_share=0.0, costs_total=costs, s_prices=s_mesh)
    oracle = closed_formula_oracle(strategy_key, legs, costs_total=costs, multiplier=multiplier)

    return {
        "strategy_key": strategy_key,
        "underlying_price": underlying_price,
        "costs_total": costs,
        "oracle": oracle,
        "payoff_curve": payoff_curve,
    }


# ---------------------------------------------------------------------------
# Complementary Architecture Endpoints (Doc v1.0)
# ---------------------------------------------------------------------------
@router.get("/health")
def get_system_health():
    """Estado integral de salud del sistema de opciones, calidad de datos y Kill Switch (Doc §4)."""
    from app.options import health
    sb = get_supabase()
    stored, _, _ = _load_stored()
    eff = sd.effective_settings(stored)
    h = health.evaluate_system_health(sb, eff)
    return {
        "status": h.status,
        "kill_switch_active": h.kill_switch_active,
        "data_state": h.data_state,
        "consecutive_divergences": h.consecutive_divergences,
        "delayed_quotes_ratio": h.delayed_quotes_ratio,
        "active_positions_count": h.active_positions_count,
        "can_open_new_position": h.can_open_new_position,
        "reasons": h.reasons,
        "checked_at": h.checked_at.isoformat(),
    }


@router.post("/control/kill-switch")
def toggle_kill_switch(payload: dict, user: dict = ceo_only):
    """Activa o desactiva el Kill Switch de emergencia de Opciones (Doc §4.2)."""
    from app.options import health
    active = bool(payload.get("active", True))
    reason = str(payload.get("reason") or "Manual toggle via API/UI")
    operator = user.get("email") if isinstance(user, dict) else "admin"
    res = health.set_kill_switch(active=active, reason=reason, operator=operator, sb=get_supabase())
    return {"ok": True, "kill_switch_active": active, "audit": res}


@router.get("/control/mode")
def get_control_mode():
    """Modo operativo del sistema de opciones y consistencia con datos (Doc §3)."""
    from app.options import health
    stored, _, _ = _load_stored()
    mode = stored.get("options_mode") or "paper"
    sb = get_supabase()
    eff = sd.effective_settings(stored)
    h = health.evaluate_system_health(sb, eff)
    coherent = True
    if mode == "paper" and h.data_state not in ("LIVE", "TEST_LIVE"):
        coherent = False
    return {
        "options_mode": mode,
        "data_state": h.data_state,
        "coherent": coherent,
        "allowed_modes": ["observation", "paper", "live_staged"],
    }


@router.put("/control/mode")
def set_control_mode(payload: dict, user: dict = ceo_only):
    """Cambia el modo operativo de opciones (Doc §3)."""
    from app.options import health
    mode = str(payload.get("mode") or "").lower()
    if mode not in ("observation", "paper", "live_staged"):
        raise HTTPException(status_code=400, detail="Modo invalido. Permitidos: observation, paper, live_staged")
    if mode == "live_staged":
        raise HTTPException(status_code=403, detail="Modo live_staged bloqueado: no habilitado en v1.0")
    reason = str(payload.get("reason") or "User mode change")
    operator = user.get("email") if isinstance(user, dict) else "admin"
    sb = get_supabase()
    stored, version, _ = _load_stored()
    new_version = version + 1
    try:
        sb.table("opt_settings").upsert([
            {"key": "options_mode", "value": mode, "updated_at": datetime.now(timezone.utc).isoformat()},
            {"key": "_version", "value": str(new_version), "updated_at": datetime.now(timezone.utc).isoformat()},
        ]).execute()
        health.record_control_event(sb, "MODE_CHANGE", f"Modo cambiado a {mode}: {reason}", operator)
    except Exception as e:
        log_warning("OPTIONS_MODE", f"Error guardando modo en BD: {e}")
    return {"ok": True, "options_mode": mode, "version": new_version}


@router.get("/control/audit")
def get_control_audit(limit: int = 50):
    """Historial de eventos de control y seguridad (Kill switch, cambios de modo, admisiones)."""
    sb = get_supabase()
    try:
        events = sb.table("opt_control_events").select("*").order("created_at", desc=True).limit(min(limit, 100)).execute().data or []
    except Exception:
        events = []
    return {"events": events}


@router.get("/events/calendar")
def get_events_calendar(symbols: str | None = None):
    """Consulta el estado del calendario de eventos corporativos y macro para simbolos dados (Doc §7)."""
    from app.options import event_calendar
    sym_list = [s.strip().upper() for s in (symbols or "SPY,QQQ,AAPL,NVDA,MSFT,AMZN,TSLA").split(",") if s.strip()]
    sb = get_supabase()
    cal = event_calendar.get_event_calendar(sb)
    results = {}
    for s in sym_list:
        ev = cal.get_event(s, horizon_days=30)
        results[s] = {
            "symbol": ev.symbol,
            "state": ev.state.value,
            "event_type": ev.event_type,
            "event_date": ev.event_date.isoformat() if ev.event_date else None,
            "source": ev.source,
            "is_blocking": ev.is_blocking(),
            "details": ev.details,
            "checked_at": ev.checked_at.isoformat() if ev.checked_at else None,
        }
    return {"events": results, "calendar_source": "hybrid (Stocks fundamentals + IBKR Scanner fallback)"}


@router.post("/evaluations/{candidate_id}/replay")
def replay_candidate_evaluation(candidate_id: int):
    """Reejecuta deterministamente la valoracion y score de una candidata (Doc §13.3)."""
    from app.options import score
    sb = get_supabase()
    stored, _, _ = _load_stored()
    eff = sd.effective_settings(stored)
    try:
        res = sb.table("opt_candidates").select("*").eq("id", candidate_id).execute().data
        if not res:
            raise HTTPException(status_code=404, detail=f"Candidata {candidate_id} no encontrada")
        cand = res[0]
        uid = cand.get("underlying_id") or 0
        und_res = sb.table("opt_underlyings").select("*").eq("id", uid).execute().data if uid else []
        und = und_res[0] if und_res else {}
        replayed = score.replay_evaluation(cand, und, eff)
        return {"ok": True, "replay": replayed}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en replay: {str(e)[:200]}")


@router.get("/analytics/portfolio-greeks")
def get_portfolio_greeks():
    """Griegas netas agregadas de la cartera de opciones abierta (Doc §8.3)."""
    from datetime import date
    from app.options import bs
    sb = get_supabase()
    try:
        open_pos = sb.table("opt_paper_trades").select("*").eq("status", "open").execute().data or []
    except Exception:
        open_pos = []

    total_delta_shares = 0.0
    total_delta_usd = 0.0
    total_gamma = 0.0
    total_vega = 0.0
    total_theta = 0.0

    position_greeks = []
    today = date.today()
    for p in open_pos:
        legs = p.get("legs") or []
        s0 = float(p.get("underlying_price") or 100.0)
        p_delta = 0.0
        p_gamma = 0.0
        p_vega = 0.0
        p_theta = 0.0
        r = 0.045
        for lg in legs:
            side = 1.0 if lg.get("side") == "buy" else -1.0
            k_strike = float(lg.get("strike") or s0)
            exp_str = lg.get("expiry") or p.get("expiry")
            t0 = 30.0 / 365.0
            if exp_str:
                try:
                    exp_date = date.fromisoformat(str(exp_str)[:10])
                    t0 = max((exp_date - today).days / 365.0, 0.001)
                except Exception:
                    pass
            iv = float(lg.get("iv") or 0.35)
            right = lg.get("right") or "C"
            d = bs.bs_delta(s0, k_strike, t0, r, iv, right) or 0.0
            g = bs.bs_gamma(s0, k_strike, t0, r, iv) or 0.0
            v = bs.bs_vega(s0, k_strike, t0, r, iv) or 0.0
            th = bs.bs_theta(s0, k_strike, t0, r, iv, right) or 0.0

            p_delta += side * 100.0 * d
            p_gamma += side * 100.0 * g
            p_vega += side * 100.0 * v
            p_theta += side * 100.0 * th

        p_delta_usd = p_delta * s0
        total_delta_shares += p_delta
        total_delta_usd += p_delta_usd
        total_gamma += p_gamma
        total_vega += p_vega
        total_theta += p_theta

        position_greeks.append({
            "id": p.get("id"),
            "symbol": p.get("symbol"),
            "strategy": p.get("strategy_type"),
            "direction": p.get("direction"),
            "underlying_price": s0,
            "delta_shares": round(p_delta, 2),
            "delta_usd": round(p_delta_usd, 2),
            "gamma": round(p_gamma, 4),
            "vega_point": round(p_vega, 2),
            "theta_day": round(p_theta, 2),
        })

    # Alertas blandas de concentracion de griegas (§8.3)
    alerts = []
    if abs(total_delta_usd) > 500.0:
        alerts.append(f"Delta neto ({total_delta_usd:+.2f} USD) con sesgo direccional significativo")
    if total_theta < -10.0:
        alerts.append(f"Decaimiento theta acelerado ({total_theta:.2f} USD/dia)")

    return {
        "portfolio_totals": {
            "open_positions": len(open_pos),
            "delta_shares": round(total_delta_shares, 2),
            "delta_usd": round(total_delta_usd, 2),
            "gamma": round(total_gamma, 4),
            "vega_point": round(total_vega, 2),
            "theta_day": round(total_theta, 2),
        },
        "alerts": alerts,
        "positions": position_greeks,
    }


@router.get("/analytics/counterfactual-book")
def get_counterfactual_book(limit: int = 50):
    """Libro contrafactual: candidatas rechazadas por ADUANA o selector vs aprobadas (Doc §12)."""
    sb = get_supabase()
    try:
        candidates = sb.table("opt_candidates").select("*").order("created_at", desc=True).limit(min(limit, 100)).execute().data or []
    except Exception:
        candidates = []

    opened_ids = set()
    try:
        pos_data = sb.table("opt_paper_trades").select("candidate_id").execute().data or []
        opened_ids = {p["candidate_id"] for p in pos_data if p.get("candidate_id")}
    except Exception:
        pass

    counterfactuals = []
    opened = []
    for c in candidates:
        cid = c.get("id")
        is_opened = cid in opened_ids
        item = {
            "id": cid,
            "symbol": c.get("symbol"),
            "strategy": c.get("strategy_type"),
            "direction": c.get("direction"),
            "ev_view_net": c.get("ev_view_net"),
            "ev_ratio": c.get("ev_ratio"),
            "score": c.get("score"),
            "ev_robust": c.get("ev_robust"),
            "eligibility_status": c.get("eligibility_status"),
            "rejection_reasons": c.get("rejection_reasons") or [],
            "created_at": c.get("created_at"),
        }
        if is_opened:
            opened.append(item)
        else:
            counterfactuals.append(item)

    return {
        "opened_count": len(opened),
        "counterfactual_count": len(counterfactuals),
        "opened_sample": opened[:20],
        "counterfactual_sample": counterfactuals[:30],
        "tracking_note": "Evaluaciones contrafactuales registradas para medir coste de oportunidad de filtros ADUANA",
    }







