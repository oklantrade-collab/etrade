from fastapi import APIRouter, Depends, HTTPException
import asyncio
import os
import json
from pydantic import BaseModel
from typing import Optional
import traceback
from datetime import datetime, date, timezone, timedelta

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase, reset_supabase
from dateutil.parser import parse as parse_dt
from app.core.market_hours import is_market_open, get_nyc_now, convert_to_lima
from app.data.ib_provider import IBProvider

# Initialize router
router = APIRouter()
_ib = IBProvider() # Shared IB connection for the API process

# CACHE LOCAL PARA REDUCIR EGRESS
METADATA_CACHE = {}
LAST_DATA_CACHE = {"data": None, "timestamp": 0}
CACHE_TTL = 5  # 5 segundos de gracia para el Dashboard

@router.get("/opportunities")
async def get_stocks_opportunities():
    """
    Get current stock opportunities and scanner results.
    Aggregates watchlist_daily + technical_scores + trade_opportunities.
    Includes retry logic for Supabase connection issues.
    """
    max_retries = 2
    for attempt in range(max_retries):
        try:
            sb = get_supabase()
            # 1. Market Status
            is_open, status_text = is_market_open()
            market_status = {
                "is_open": is_open,
                "status": status_text,
                "nyc_now": get_nyc_now().isoformat()
            }

            # 2. Get today's date in Lima/NYC
            today = get_nyc_now().date().isoformat()

            # 3. Fetch Technical Scores (Most recent)
            res_tech = sb.table("technical_scores")\
                .select("*")\
                .order("timestamp", desc=True)\
                .limit(100)\
                .execute()
            
            tech_data = res_tech.data or []

            # 3.5 Fetch Queue Statuses to join
            q_res = sb.table("stocks_priority_queue")\
                .select("ticker, status, is_overbought")\
                .execute()
            q_map = {r["ticker"]: r for r in (q_res.data or [])}
            
            # 3.6 Fetch Open Positions to correct status
            pos_res = sb.table("stocks_positions")\
                .select("ticker")\
                .eq("status", "open")\
                .execute()
            owned_tickers = {p["ticker"] for p in (pos_res.data or [])}
            
            # FLATTEN signals_json into the root for the Dashboard
            flattened = []
            for item in tech_data:
                try:
                    sigs = item.get("signals_json")
                    if isinstance(sigs, str):
                        try: sigs = json.loads(sigs)
                        except: sigs = {}
                    
                    if not sigs or not isinstance(sigs, dict):
                        sigs = {}
                    
                    # Combine item and sigs
                    merged = {**item, **sigs}
                    merged["ticker"] = item.get("ticker") or sigs.get("ticker", "UNKNOWN")
                    merged["created_at"] = item.get("timestamp")
                    
                    # Ensure last_scan_time is present (extract from timestamp if missing)
                    ts = item.get("timestamp")
                    if not merged.get("last_scan_time") and ts:
                        try:
                            dt = parse_dt(ts)
                            dt_lima = convert_to_lima(dt)
                            merged["last_scan_time"] = dt_lima.strftime("%H:%M")
                        except:
                            merged["last_scan_time"] = "--:--"
                    
                    if not merged.get("last_scan_time"):
                        merged["last_scan_time"] = "--:--"

                    # Join Queue Status
                    q_info = q_map.get(merged["ticker"], {})
                    
                    if merged["ticker"] in owned_tickers:
                        merged["queue_status"] = "owned"
                    else:
                        merged["queue_status"] = q_info.get("status", "watching")

                    merged["is_overbought_queue"] = q_info.get("is_overbought", False)

                    flattened.append(merged)
                except Exception as item_e:
                    log_warning("stocks_api", f"Error processing item {item.get('ticker')}: {item_e}")
                    continue

            return {
                "opportunities": flattened,
                "total": len(flattened),
                "market_status": market_status
            }
        except Exception as e:
            if attempt < max_retries - 1 and ("10061" in str(e) or "disconnected" in str(e)):
                reset_supabase()
                await asyncio.sleep(1)
                continue
            log_error("stocks_api", f"Error in get_stocks_opportunities: {e}")
            return {"opportunities": [], "total": 0, "market_status": {"is_open": False, "status": "ERROR"}}

@router.get("/positions")
async def get_stocks_positions():
    """
    Get active stock positions (INTERNAL ONLY).
    Optimized to read ONLY from DB with retry logic.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            sb = get_supabase()
            # 1. Fetch all open positions
            res = sb.table("stocks_positions")\
                .select("*")\
                .eq("status", "open")\
                .order("first_buy_at", desc=True)\
                .execute()
            
            positions = res.data or []
            if not positions:
                return {"positions": []}

            tickers = [p["ticker"] for p in positions]

            # 2. Bulk fetch strategy info from orders
            strategy_map = {}
            try:
                order_res = sb.table("stocks_orders")\
                    .select("ticker, rule_code")\
                    .in_("ticker", tickers)\
                    .eq("direction", "buy")\
                    .order("created_at", desc=True)\
                    .execute()
                for o in (order_res.data or []):
                    if o["ticker"] not in strategy_map:
                        strategy_map[o["ticker"]] = o["rule_code"]
            except: pass

            # 2.5 Try to connect to IB if not connected
            try:
                if _ib.conn and not _ib.conn.connected:
                    # Async connection attempt (non-blocking if it fails)
                    _ib.conn.connect_tws(client_id=99)
            except: pass

            # 3. Assemble with Live Prices from IB
            tickers = [p["ticker"] for p in positions]
            live_prices = await _ib.get_multiple_prices(tickers)

            for pos in positions:
                ticker = pos["ticker"]
                
                # Obtener precio real de IB (en memoria)
                cur_price = live_prices.get(ticker, 0)
                
                # Fallback a DB si IB no tiene el dato todavía
                if cur_price <= 0:
                    cur_price = float(pos.get("current_price") or pos.get("avg_price") or 0)
                
                avg_entry = float(pos.get("avg_price") or 0)
                shares = float(pos.get("shares") or 0)

                pos["company_name"] = ticker
                pos["sector"] = "Stocks"
                pos["side"] = "buy"
                pos["strategy"] = strategy_map.get(ticker) or "V5_INDUSTRIAL"
                pos["current_price"] = round(cur_price, 2)
                
                pos["unrealized_pnl"] = round((cur_price - avg_entry) * shares, 2)
                pos["unrealized_pnl_pct"] = round(((cur_price - avg_entry) / avg_entry * 100), 2) if avg_entry > 0 else 0
                pos["total_cost"] = round(avg_entry * shares, 2)

            return {"positions": positions}

        except Exception as e:
            if attempt < max_retries - 1 and ("10061" in str(e) or "disconnected" in str(e)):
                reset_supabase()
                await asyncio.sleep(1)
                continue
            log_error("stocks_api", f"Error in get_stocks_positions: {e}")
            return {"positions": [], "error": str(e)}

@router.get("/status")
async def get_stocks_status():
    """Get overall status of the stocks engine."""
    try:
        sb = get_supabase()
        config_res = sb.table("stocks_config").select("*").execute()
        config = {r["key"]: r["value"] for r in (config_res.data or [])}
        
        return {
            "capital_usd": float(config.get("total_capital", 5000)),
            "universe_size": 0,
            "paper_mode": config.get("execution_mode", "paper") == "paper",
            "max_risk_pct": float(config.get("max_risk_pct", 60))
        }
    except Exception as e:
        log_error("stocks_api", f"Error in get_stocks_status: {e}")
        return {"capital_usd": 5000, "universe_size": 0, "paper_mode": True}

@router.get("/journal")
async def get_stocks_journal(limit: int = 50):
    """Get trade journal history from closed positions with retry logic."""
    max_retries = 2
    for attempt in range(max_retries):
        try:
            sb = get_supabase()
            res = sb.table("trades_journal")\
                .select("*")\
                .order("exit_date", desc=True)\
                .limit(limit)\
                .execute()
            
            journal = res.data or []
            sanitized_journal = []
            
            for entry in journal:
                try:
                    # Priorizar trade_type que es el campo real en la DB
                    entry["strategy"] = entry.get("trade_type") or entry.get("strategy") or entry.get("rule_code") or "V5_INDUSTRIAL"
                    entry["exit_strategy"] = entry.get("exit_reason") or "CLOSED"
                    entry["updated_at"] = entry.get("exit_date")
                    entry["first_buy_at"] = entry.get("entry_date")
                    
                    # Asegurar valores numéricos con fallbacks seguros
                    def to_f(val):
                        try: return float(val) if val is not None else 0.0
                        except: return 0.0

                    entry["unrealized_pnl"] = to_f(entry.get("pnl_usd"))
                    entry["unrealized_pnl_pct"] = to_f(entry.get("pnl_pct"))
                    entry["avg_price"] = to_f(entry.get("entry_price"))
                    entry["exit_price"] = to_f(entry.get("exit_price"))
                    entry["shares"] = int(to_f(entry.get("shares")))
                    entry["total_cost"] = entry["avg_price"] * entry["shares"]
                    entry["company_name"] = entry.get("ticker", "UNKNOWN")
                    entry["status"] = "closed"
                    
                    sanitized_journal.append(entry)
                except Exception as item_e:
                    log_warning("stocks_api", f"Skipping journal item due to error: {item_e}")
                    continue
                
            return sanitized_journal
        except Exception as e:
            if attempt < max_retries - 1 and ("10061" in str(e) or "disconnected" in str(e)):
                reset_supabase()
                await asyncio.sleep(1)
                continue
            log_error("stocks_api", f"Error in journal: {e}")
            return []

@router.get("/rules")
async def get_stocks_rules():
    """Get all stocks trading rules from stocks_rules table."""
    try:
        sb = get_supabase()
        res = sb.table("stocks_rules").select("*").order("rule_code").execute()
        return res.data or []
    except Exception as e:
        log_error("stocks_api", f"Error in get_stocks_rules: {e}")
        return []

@router.put("/rules/{rule_code}")
async def update_stocks_rule(rule_code: str, payload: dict):
    """Update an existing stocks rule."""
    try:
        sb = get_supabase()
        # Campos permitidos para actualización (evitar sobreescritura accidental)
        allowed = {
            "name", "enabled", "ia_min", "tech_score_min", "fundamental_score_min",
            "movements_allowed", "notes", "order_type", "limit_trigger_pct",
            "dca_enabled", "dca_max_buys", "dca_min_drop_pct"
        }
        update_data = {k: v for k, v in payload.items() if k in allowed}
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        res = sb.table("stocks_rules").update(update_data).eq("rule_code", rule_code).execute()
        if res.data:
            return {"success": True, "rule": res.data[0]}
        else:
            raise HTTPException(status_code=404, detail="Regla no encontrada")
    except Exception as e:
        log_error("stocks_api", f"Error updating rule {rule_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/universe")
async def get_stocks_universe():
    """Get the daily watchlist/universe from watchlist_daily."""
    try:
        sb = get_supabase()
        today = get_nyc_now().date().isoformat()
        
        # Intentar obtener lo de hoy
        res = sb.table("watchlist_daily")\
            .select("*")\
            .eq("date", today)\
            .order("fundamental_score", desc=True)\
            .execute()
        
        data = res.data or []
        
        # Si no hay hoy, buscar lo más reciente
        if not data:
            res_recent = sb.table("watchlist_daily")\
                .select("*")\
                .order("date", desc=True)\
                .limit(50)\
                .execute()
            data = res_recent.data or []
            
        return {"universe": data, "count": len(data), "date": data[0]["date"] if data else today}
    except Exception as e:
        log_error("stocks_api", f"Error in get_stocks_universe: {e}")
        return {"universe": [], "count": 0, "error": str(e)}

@router.post("/refresh-fundamentals")
async def refresh_stocks_fundamentals():
    """Trigger a manual refresh of the universe fundamentals."""
    try:
        from app.stocks.universe_builder import UniverseBuilder
        builder = UniverseBuilder()
        # Esto es asíncrono pero lo esperamos para confirmar a la UI
        await builder.build_daily_watchlist()
        return {"success": True, "message": "Universe rebuilt successfully"}
    except Exception as e:
        log_error("stocks_api", f"Error refreshing fundamentals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/positions/{position_id}")
async def delete_stock_position(position_id: str):
    """Hard delete a stock position record."""
    try:
        sb = get_supabase()
        res = sb.table("stocks_positions").delete().eq("id", position_id).execute()
        
        # En la versión actual de la lib de Supabase, .data contiene los registros afectados
        if res.data:
            log_info("stocks_api", f"Position {position_id} deleted successfully")
            return {"success": True, "message": "Record deleted"}
        else:
            # Podría ser exitoso pero sin devolver data, o simplemente no encontrarlo
            # Verificamos si hubo un error en la ejecución
            return {"success": True, "message": "Delete command executed"}
            
    except Exception as e:
        log_error("stocks_api", f"Error deleting position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar registro: {str(e)}")

@router.post("/positions/{position_id}/close")
async def manual_close_stock_position(position_id: str):
    """Manually close a stock position (updates status to 'closed')."""
    try:
        sb = get_supabase()
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        
        # 1. Obtener la posición
        res = sb.table("stocks_positions").select("*").eq("id", position_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Posición no encontrada")
        
        pos = res.data[0]
        ticker = pos["ticker"]
        avg_price = float(pos.get("avg_price") or 0)
        shares = float(pos.get("shares") or 0)
        
        # 2. Obtener precio actual (de snapshot)
        snap_res = sb.table("market_snapshot").select("price").eq("symbol", ticker).execute()
        current_price = float(snap_res.data[0]["price"]) if snap_res.data else avg_price
        
        # 3. Calcular PnL Realizado
        pnl_usd = (current_price - avg_price) * shares
        pnl_pct = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
        
        # 4. Actualizar registro a 'closed'
        update_res = sb.table("stocks_positions").update({
            "status": "closed",
            "updated_at": now,
            "exit_price": current_price,
            "close_reason": "MANUAL_CLOSE",
            "unrealized_pnl": round(pnl_usd, 2),
            "unrealized_pnl_pct": round(pnl_pct, 2)
        }).eq("id", position_id).execute()
        
        # 5. Registrar en Journal para que aparezca en "Closed History"
        try:
            journal_entry = {
                "ticker": ticker,
                "shares": int(shares),
                "entry_price": avg_price,
                "exit_price": current_price,
                "entry_date": pos.get("first_buy_at") or pos.get("entry_date"),
                "exit_date": now,
                "pnl_usd": round(pnl_usd, 2),
                "pnl_pct": round(pnl_pct, 2),
                "result": "win" if pnl_usd > 0 else "loss",
                "exit_reason": "MANUAL_CLOSE",
                "trade_type": pos.get("strategy") or pos.get("rule_code") or "V5_INDUSTRIAL"
            }
            sb.table("trades_journal").insert(journal_entry).execute()
            log_info("stocks_api", f"Manual close for {ticker} recorded in journal")
        except Exception as journal_e:
            log_error("stocks_api", f"Error recording manual close in journal for {ticker}: {journal_e}")
        
        return {"success": True, "pnl_usd": pnl_usd}
        
    except Exception as e:
        log_error("stocks_api", f"Error closing position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/priority-queue")
async def get_priority_queue():
    """Get current APEX priority queue for the dashboard.
    
    Enhanced to:
      - Auto-clean stale 'buying' entries (>30 min without completion)
      - Mark owned tickers as 'owned'
      - Dynamically populate from market_snapshot APEX data when queue is stale
    """
    try:
        sb = get_supabase()

        # 0. Get owned tickers to exclude/mark
        pos_res = sb.table("stocks_positions")\
            .select("ticker")\
            .eq("status", "open")\
            .execute()
        owned_tickers = {p["ticker"] for p in (pos_res.data or [])}

        # 1. Auto-clean stale "buying" entries (stuck >30 min)
        try:
            stale_res = sb.table("stocks_priority_queue")\
                .select("id, ticker, status, last_updated")\
                .eq("status", "buying")\
                .execute()
            
            now = datetime.now(timezone.utc)
            for item in (stale_res.data or []):
                last_upd = item.get("last_updated")
                if last_upd:
                    try:
                        upd_dt = parse_dt(last_upd)
                        if upd_dt.tzinfo is None:
                            upd_dt = upd_dt.replace(tzinfo=timezone.utc)
                        age_mins = (now - upd_dt).total_seconds() / 60
                        
                        if item["ticker"] in owned_tickers:
                            # Actually bought — mark as owned
                            sb.table("stocks_priority_queue").update({
                                "status": "owned",
                                "last_updated": now.isoformat()
                            }).eq("id", item["id"]).execute()
                        elif age_mins > 30:
                            # Stuck in buying — revert to watching
                            sb.table("stocks_priority_queue").update({
                                "status": "watching",
                                "last_updated": now.isoformat(),
                                "capital_assigned": 0,
                                "shares_target": 0
                            }).eq("id", item["id"]).execute()
                            log_warning("stocks_api", f"Cleaned stale 'buying' entry: {item['ticker']} (age={age_mins:.0f}m)")
                    except Exception:
                        pass
        except Exception as clean_e:
            log_warning("stocks_api", f"Error cleaning stale queue: {clean_e}")

        # 2. Get queue items (excluding owned)
        q_res = sb.table("stocks_priority_queue") \
            .select("*") \
            .in_("status", ["pending", "buying", "blocked", "watching"]) \
            .order("composite_rank", desc=True) \
            .limit(20) \
            .execute()

        queue = q_res.data or []
        
        # Filter out owned tickers from the display queue
        queue = [q for q in queue if q["ticker"] not in owned_tickers]

        # 3. If queue is too small, generate dynamic candidates from market_snapshot
        if len(queue) < 5:
            try:
                # Get top APEX-scoring tickers from market_snapshot
                existing_tickers = {q["ticker"] for q in queue} | owned_tickers
                
                limit_time_iso = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
                
                snap_res = sb.table("market_snapshot")\
                    .select("symbol, price, apex_4h, apex_1d, apex_signal, apex_conf")\
                    .not_.is_("apex_4h", "null")\
                    .gt("updated_at", limit_time_iso)\
                    .order("apex_4h", desc=True)\
                    .limit(30)\
                    .execute()
                
                for snap in (snap_res.data or []):
                    if len(queue) >= 10:
                        break
                    ticker = snap.get("symbol")
                    if not ticker or ticker in existing_tickers:
                        continue
                    
                    apex_4h = float(snap.get("apex_4h") or 0)
                    apex_1d = float(snap.get("apex_1d") or 0)
                    
                    # Only include decent APEX scores
                    if apex_4h < 60:
                        continue
                    
                    # Build a dynamic queue entry
                    dynamic_entry = {
                        "ticker": ticker,
                        "group_name": "",
                        "apex_score_4h": apex_4h,
                        "apex_score_1d": apex_1d,
                        "return_expected": 0,
                        "confidence": snap.get("apex_conf") or "medium",
                        "composite_rank": round(apex_4h * 0.6 + apex_1d * 0.4, 2),
                        "status": "watching",
                        "entry_reason": "dynamic_scan",
                        "triggered_rule": None,
                        "is_overbought": False,
                        "rsi_at_entry": 0,
                        "fib_zone": 0,
                        "capital_assigned": 0,
                        "shares_target": 0,
                        "price_at_rank": float(snap.get("price") or 0),
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                    }
                    queue.append(dynamic_entry)
                    existing_tickers.add(ticker)
                
                # Re-sort by composite_rank
                queue.sort(key=lambda q: float(q.get("composite_rank") or 0), reverse=True)
            except Exception as dyn_e:
                log_warning("stocks_api", f"Dynamic queue generation error: {dyn_e}")

        # 4. Capital summary
        try:
            from app.stocks.stocks_orchestrator import (
                load_orchestrator_config,
                calculate_available_capital,
            )
            cfg = await load_orchestrator_config(sb)
            capital = await calculate_available_capital(cfg, sb)
        except Exception:
            capital = {
                'capital_available': 0,
                'capital_max_total': 0,
                'capital_invested': 0,
                'ops_possible': 0,
                'can_buy': False,
                'reason': 'Config not loaded',
            }

        return {
            "queue": queue,
            "capital": capital,
            "summary": {
                "total": len(queue),
                "active": sum(1 for q in queue if not q.get("is_overbought")),
                "blocked": sum(1 for q in queue if q.get("is_overbought")),
                "with_signal": sum(1 for q in queue if q.get("triggered_rule")),
            }
        }
    except Exception as e:
        log_error("stocks_api", f"Error in get_priority_queue: {e}")
        return {"queue": [], "capital": {}, "summary": {"total": 0, "active": 0, "blocked": 0, "with_signal": 0}}

