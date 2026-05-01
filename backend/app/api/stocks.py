
from fastapi import APIRouter, Depends, HTTPException
import asyncio
import os
from pydantic import BaseModel
from typing import Optional
import traceback
from datetime import datetime, date, timezone, timedelta

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from dateutil.parser import parse as parse_dt

router = APIRouter()

@router.get("/positions")
async def get_stocks_positions():
    """
    Get active stock positions (INTERNAL ONLY).
    Optimized to read ONLY from DB to avoid timeouts.
    """
    sb = get_supabase()
    try:
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

        # 3. Assemble (No external API calls here!)
        for pos in positions:
            ticker = pos["ticker"]
            cur_price = float(pos.get("current_price") or pos.get("avg_price") or 0)
            avg_entry = float(pos.get("avg_price") or 0)
            shares = float(pos.get("shares") or 0)

            # Map fields for frontend
            pos["company_name"] = ticker
            pos["sector"] = "Stocks"
            pos["side"] = "buy"
            pos["strategy"] = strategy_map.get(ticker) or "HOT_CANDLE"
            
            # Calculations
            pos["unrealized_pnl"] = round((cur_price - avg_entry) * shares, 2)
            pos["unrealized_pnl_pct"] = round(((cur_price - avg_entry) / avg_entry * 100), 2) if avg_entry > 0 else 0
            pos["total_cost"] = round(avg_entry * shares, 2)

        return {"positions": positions}

    except Exception as e:
        log_error("stocks_api", f"Error in get_stocks_positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/journal")
async def get_stocks_journal(limit: int = 50):
    """Get trade journal history from closed positions."""
    sb = get_supabase()
    try:
        res = sb.table("stocks_positions")\
            .select("*")\
            .eq("status", "closed")\
            .order("updated_at", desc=True)\
            .limit(limit)\
            .execute()
        return res.data or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance")
async def get_stocks_performance():
    """Get performance metrics for the stocks industrial engine."""
    sb = get_supabase()
    try:
        res = sb.table("stocks_positions").select("*").eq("status", "closed").execute()
        trades = res.data or []
        total = len(trades)
        wins = sum(1 for t in trades if float(t.get("unrealized_pnl") or 0) > 0)
        pnl_total = sum(float(t.get("unrealized_pnl") or 0) for t in trades)
        
        return {
            "total_trades": total,
            "win_rate": round((wins/total*100), 2) if total > 0 else 0,
            "total_pnl": round(pnl_total, 2),
            "trades": trades[:10]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
