from fastapi import APIRouter, Depends, HTTPException
import asyncio
import os
from pydantic import BaseModel
from typing import Optional
import traceback
from datetime import datetime, date, timezone, timedelta

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase, reset_supabase
from dateutil.parser import parse as parse_dt
from app.core.market_hours import is_market_open, get_nyc_now

# Initialize router
router = APIRouter()

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
            
            return {
                "opportunities": tech_data,
                "total": len(tech_data),
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
                .select("id, ticker, status, shares, avg_price, current_price, unrealized_pnl, unrealized_pnl_pct, stop_loss, take_profit, trailing_sl_price, sl_dynamic_price, highest_price_reached, sl_type, recovery_mode, slv_price")\
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

            # 3. Assemble
            for pos in positions:
                ticker = pos["ticker"]
                cur_price = float(pos.get("current_price") or pos.get("avg_price") or 0)
                avg_entry = float(pos.get("avg_price") or 0)
                shares = float(pos.get("shares") or 0)

                pos["company_name"] = ticker
                pos["sector"] = "Stocks"
                pos["side"] = "buy"
                pos["strategy"] = strategy_map.get(ticker) or "V5_INDUSTRIAL"
                
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
                
            return journal
        except Exception as e:
            if attempt < max_retries - 1 and ("10061" in str(e) or "disconnected" in str(e)):
                reset_supabase()
                await asyncio.sleep(1)
                continue
            log_error("stocks_api", f"Error in journal: {e}")
            return []
