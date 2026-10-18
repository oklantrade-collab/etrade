"""Options Worker local (corre junto al Stocks Worker; unico proceso de Options con acceso a TWS).

- Heartbeat en opt_worker_heartbeat.
- Toma jobs de opt_jobs (scan, snapshot, g1_probe) y los ejecuta.
- Grabador de snapshots periodico dentro del horario de mercado.
- Jamas envia ordenes (adaptador de solo lectura).

Uso:  python -m app.options.worker
"""
from __future__ import annotations

import os
import time
import traceback
from datetime import datetime, timezone

from app.core.logger import log_error, log_info, log_warning
from app.core.market_hours import is_market_open
from app.core.supabase_client import get_supabase
from app.options import settings_defaults as sd
from app.options.ib_client import IBSession
from app.options.candidates import generate_all, run_portfolio_selection
from app.options.exit_engine import process_open_positions
from app.options.scanner import record_snapshots, run_scan

MODULE = "OPTIONS_WORKER"
POLL_SEC = 5
HEARTBEAT_SEC = 30


def _load_effective(sb) -> dict:
    try:
        rows = sb.table("opt_settings").select("key,value").execute().data or []
        stored = {r["key"]: r["value"] for r in rows if r["key"] != "_version"}
    except Exception:
        stored = {}
    return sd.effective_settings(stored)


def _settings_version(sb) -> int:
    try:
        r = sb.table("opt_settings").select("value").eq("key", "_version").execute().data
        return int(r[0]["value"]) if r else 0
    except Exception:
        return 0


def _heartbeat(sb, ib: IBSession, status: str, detail: dict | None = None, data_state: str | None = None):
    try:
        sb.table("opt_worker_heartbeat").upsert({
            "worker": "options_worker", "status": status, "data_state": data_state or "UNKNOWN",
            "detail": {"tws_connected": ib.is_connected(), **(detail or {})},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="worker").execute()
    except Exception as e:
        log_warning(MODULE, f"heartbeat fallo: {e}")


def _claim_job(sb) -> dict | None:
    """Toma el job pendiente mas antiguo (update condicional por status para evitar doble toma)."""
    rows = sb.table("opt_jobs").select("*").eq("status", "pending").order("created_at").limit(1).execute().data or []
    if not rows:
        return None
    job = rows[0]
    res = (sb.table("opt_jobs").update({"status": "running", "started_at": datetime.now(timezone.utc).isoformat()})
           .eq("id", job["id"]).eq("status", "pending").execute().data)
    return job if res else None


def _finish(sb, job_id: int, ok: bool, result: dict | None = None, error: str | None = None):
    sb.table("opt_jobs").update({
        "status": "done" if ok else "error", "result": result, "error": error,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job_id).execute()


def _data_state(sb) -> str:
    try:
        r = sb.table("opt_quotes_latest").select("market_data_type").order("received_at", desc=True).limit(1).execute().data
        return r[0]["market_data_type"] if r else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def main():
    if not sd.execution_mode_ok():
        raise SystemExit("OPTIONS_EXECUTION_MODE invalido: solo 'paper'. Worker no arranca.")
    if not sd.options_enabled():
        raise SystemExit("OPTIONS_ENABLED=false: Worker no arranca.")
    sb = get_supabase()
    eff = _load_effective(sb)
    ib = IBSession(allow_delayed=bool(eff["allow_delayed_data"]))
    log_info(MODULE, f"Iniciando Options Worker (paper, delayed={eff['allow_delayed_data']}, clientId={ib.client_id})")

    last_hb = last_snap = last_cleanup = 0.0
    while True:
        try:
            now = time.time()
            if now - last_hb >= HEARTBEAT_SEC:
                _heartbeat(sb, ib, "running", data_state=_data_state(sb))
                last_hb = now

            if now - last_cleanup >= 21600:  # Cada 6 horas: purga de snapshots y candidatas descartadas
                last_cleanup = now
                try:
                    from datetime import timedelta
                    cutoff_snap = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                    cutoff_cand = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
                    sb.table("opt_snapshots").delete().lt("captured_at", cutoff_snap).execute()
                    sb.table("opt_candidates").delete().in_("eligibility_status", ["rejected", "expired"]).lt("created_at", cutoff_cand).execute()
                    log_info(MODULE, "Mantenimiento preventivo Supabase Free: purga de snapshots (>7d) y descartes (>3d)")
                except Exception as e:
                    log_warning(MODULE, f"Mantenimiento preventivo fallo (no critico): {e}")

            job = _claim_job(sb)
            if job:
                eff = _load_effective(sb)
                ib.allow_delayed = bool(eff["allow_delayed_data"])
                log_info(MODULE, f"Job {job['id']} ({job['type']})")
                try:
                    ver = _settings_version(sb)
                    if job["type"] == "candidates":          # solo lee Supabase: no requiere TWS
                        res = generate_all(sb, eff, ver)
                    elif job["type"] == "portfolio_select":  # solo lee Supabase: no requiere TWS
                        res = run_portfolio_selection(sb, eff, ver)
                    elif job["type"] == "exit_check":        # solo lee Supabase: no requiere TWS
                        res = process_open_positions(sb, eff)
                    else:
                        if not ib.ensure_connected():
                            raise RuntimeError("No se pudo conectar a TWS")
                        if job["type"] == "scan":
                            syms = (job.get("params") or {}).get("symbols")
                            res = run_scan(ib, sb, eff, symbols=syms)
                            res["candidates"] = generate_all(sb, eff, ver)
                        elif job["type"] in ("snapshot", "chain_sync"):
                            res = record_snapshots(ib, sb, eff)
                            res["candidates"] = generate_all(sb, eff, ver)
                        else:
                            raise ValueError(f"tipo de job no soportado aun: {job['type']}")
                    _finish(sb, job["id"], True, result=res)
                except Exception as e:
                    log_error(MODULE, f"Job {job['id']} fallo: {e}")
                    _finish(sb, job["id"], False, error=str(e)[:500])
                continue

            freq = int(eff["snapshot_freq_min"]) * 60
            if now - last_snap >= freq and is_market_open():
                last_snap = now
                if ib.ensure_connected():
                    res = record_snapshots(ib, sb, eff)
                    _heartbeat(sb, ib, "running", {"last_snapshot": res}, data_state=_data_state(sb))
                else:
                    _heartbeat(sb, ib, "tws_down")
            time.sleep(POLL_SEC)
        except KeyboardInterrupt:
            log_info(MODULE, "Detenido por el usuario")
            ib.close()
            break
        except Exception:
            log_error(MODULE, f"Error en bucle: {traceback.format_exc()[-400:]}")
            time.sleep(10)


if __name__ == "__main__":
    main()
