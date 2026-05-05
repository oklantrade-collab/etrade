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
                .limit(50)\
                .execute()
            
            tech_data = res_tech.data or []
            
            # FLATTEN signals_json into the root for the Dashboard
            flattened = []
            for item in tech_data:
                sigs = item.get("signals_json")
                if isinstance(sigs, str):
                    try: sigs = json.loads(sigs)
                    except: sigs = {}
                
                if not sigs or not isinstance(sigs, dict):
                    sigs = {}
                
                # Combine item and sigs
                merged = {**item, **sigs}
                merged["created_at"] = item.get("timestamp")
                
                # Ensure last_scan_time is present (extract from timestamp if missing)
                if not merged.get("last_scan_time") and item.get("timestamp"):
                    try:
                        dt = parse_dt(item["timestamp"])
                        dt_lima = convert_to_lima(dt)
                        merged["last_scan_time"] = dt_lima.strftime("%H:%M")
                    except:
                        pass
                
                flattened.append(merged)

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
                    _ib.conn.connect_tws()
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
            for entry in journal:
                entry["strategy"] = entry.get("strategy") or entry.get("rule_code") or "V5_INDUSTRIAL"
                entry["exit_strategy"] = entry.get("exit_reason") or "CLOSED"
                entry["updated_at"] = entry.get("exit_date")
                entry["first_buy_at"] = entry.get("entry_date")
                entry["unrealized_pnl"] = entry.get("pnl_usd")
                entry["unrealized_pnl_pct"] = entry.get("pnl_pct")
                
                # Campos faltantes para el modal de detalle
                entry["avg_price"] = entry.get("entry_price")
                entry["shares"] = entry.get("shares") or 0
                entry["total_cost"] = (entry.get("entry_price") or 0) * (entry.get("shares") or 0)
                entry["company_name"] = entry.get("ticker")
                entry["status"] = "closed"
                
            return journal
        except Exception as e:
            if attempt < max_retries - 1 and ("10061" in str(e) or "disconnected" in str(e)):
                reset_supabase()
                await asyncio.sleep(1)
                continue
            log_error("stocks_api", f"Error in journal: {e}")
            return []

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
        
        # 5. Registrar en Journal (Opcional, si el sistema lo requiere duplicado)
        # Por ahora solo movemos el estado.
        
        return {"success": True, "pnl_usd": pnl_usd}
        
    except Exception as e:
        log_error("stocks_api", f"Error closing position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
