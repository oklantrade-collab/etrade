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

    return {
        "module_enabled": sd.options_enabled(),
        "execution_mode": sd.EXECUTION_MODE,
        "execution_mode_ok": sd.execution_mode_ok(),
        "paper": True,
        "hard_caps": caps,
        "worker": {"state": worker_state, "data_state": (worker or {}).get("data_state") or "UNKNOWN", "error": worker_err},
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
    return {**rows[0], "payoff": payoff_curve(rows[0]), "simulation": sim[0] if sim else None, "aduana": dec[0] if dec else None}


# ---------------------------------------------------------------------------
# Sprint 5: Opportunities & Portfolio Selector
# ---------------------------------------------------------------------------
@router.get("/opportunities")
def list_opportunities(strategy: str | None = None, direction: str | None = None,
                       status: str = "all", symbol: str | None = None, min_score: float | None = None,
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
        items = q.order("score", desc=True).limit(min(limit, 300)).execute().data or []
    except Exception as e:
        return {"items": [], "error": str(e)[:200]}

    if symbol:
        items = [i for i in items if (i.get("opt_underlyings") or {}).get("symbol") == symbol.upper()]

    total = len(items)
    selected = [i for i in items if i.get("eligibility_status") == "selected"]
    eligible = [i for i in items if i.get("eligibility_status") == "eligible"]
    rejected = [i for i in items if i.get("eligibility_status") == "rejected"]

    calls = [i for i in items if (i.get("direction") or "").lower() in ("bullish", "call")]
    puts = [i for i in items if (i.get("direction") or "").lower() in ("bearish", "put")]
    top_calls = sorted(calls, key=lambda x: float(x.get("score") or 0.0), reverse=True)[:3]
    top_puts = sorted(puts, key=lambda x: float(x.get("score") or 0.0), reverse=True)[:3]

    allocated_risk = sum(float(s.get("max_loss_total") or 0.0) for s in selected)
    max_open_risk = float(eff.get("max_open_risk_usd") or 100.0)
    remaining_budget = max(0.0, max_open_risk - allocated_risk)

    return {
        "items": items,
        "summary": {
            "total_candidates": total,
            "total_calls": len(calls),
            "total_puts": len(puts),
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

    return {"ok": True, "position": inserted}


@router.post("/positions/{position_id}/simulate-exit")
def simulate_exit(position_id: int, payload: dict | None = None, user: dict = ceo_only):
    """Simula la salida manual de una posicion paper."""
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
    exit_fill = pe.simulate_exit_fill(pos, None, eff, reason, adverse=False, now=now_dt)

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
        "exit_reason": reason,
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







