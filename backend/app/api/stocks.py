
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
from app.core.market_hours import is_market_open, get_nyc_now

router = APIRouter()


@router.get("/opportunities")
async def get_stocks_opportunities():
    """
    Get current stock opportunities and scanner results.
    Aggregates watchlist_daily + technical_scores + trade_opportunities.
    """
    sb = get_supabase()
    try:
        # 1. Market Status
        is_open, status_text = is_market_open()
        market_status = {
            "is_open": is_open,
            "status": status_text,
            "nyc_now": get_nyc_now().isoformat()
        }

        # 2. Get today's date in Lima/NYC (same for stocks purposes usually)
        today = get_nyc_now().date().isoformat()

        # 3. Fetch Watchlist
        wl_res = sb.table("watchlist_daily")\
            .select("*")\
            .eq("date", today)\
            .order("catalyst_score", desc=True)\
            .execute()
        
        watchlist = wl_res.data or []
        if not watchlist:
            # Fallback to last 2 days if today is empty
            yesterday = (get_nyc_now() - timedelta(days=2)).date().isoformat()
            wl_res = sb.table("watchlist_daily")\
                .select("*")\
                .gte("date", yesterday)\
                .order("date", desc=True)\
                .order("catalyst_score", desc=True)\
                .limit(100)\
                .execute()
            watchlist = wl_res.data or []

        if not watchlist:
            return {"opportunities": [], "total": 0, "market_status": market_status}

        tickers = [w["ticker"] for w in watchlist]

        # 4. Fetch Technical Scores (Bulk)
        tech_res = sb.table("technical_scores")\
            .select("*")\
            .in_("ticker", tickers)\
            .order("timestamp", desc=True)\
            .execute()
        
        # Map latest score per ticker
        tech_map = {}
        for t in (tech_res.data or []):
            if t["ticker"] not in tech_map:
                tech_map[t["ticker"]] = t

        # 5. Fetch Active Opportunities (for entry/sl/tp)
        opp_res = sb.table("trade_opportunities")\
            .select("*")\
            .in_("ticker", tickers)\
            .eq("status", "active")\
            .execute()
        opp_map = {o["ticker"]: o for o in (opp_res.data or [])}

        # 6. Fetch Recent Orders (for activity indicator)
        order_res = sb.table("stocks_orders")\
            .select("*")\
            .in_("ticker", tickers)\
            .order("created_at", desc=True)\
            .limit(200)\
            .execute()
        order_map = {}
        for o in (order_res.data or []):
            if o["ticker"] not in order_map:
                order_map[o["ticker"]] = []
            if len(order_map[o["ticker"]]) < 5:
                order_map[o["ticker"]].append(o)

        # 7. Assemble final list
        final_list = []
        for w in watchlist:
            ticker = w["ticker"]
            tech = tech_map.get(ticker, {})
            opp = opp_map.get(ticker, {})
            
            # Format time for frontend
            last_scan = "—:—"
            if tech.get("timestamp"):
                try:
                    ts_str = tech["timestamp"].replace("Z", "+00:00")
                    dt = datetime.fromisoformat(ts_str)
                    # Convert to local time (Lima) - same as NYC roughly for hours
                    last_scan = (dt - timedelta(hours=5)).strftime("%H:%M")
                except: pass

            item = {
                "ticker": ticker,
                "company_name": w.get("company_name") or ticker,
                "price": float(tech.get("price") or 0),
                "change_pct": float(tech.get("change_pct") or 0),
                "volume": float(tech.get("volume") or 0),
                "rvol": float(tech.get("rvol") or 1.0),
                "rev_growth": float(w.get("revenue_growth_yoy") or 0),
                "piotroski_score": int(tech.get("piotroski_score") or 0),
                "piotroski_detail": tech.get("piotroski_detail"),
                "is_pro_member": "GIANT" in (w.get("pool_type") or "") or "LEADER" in (w.get("pool_type") or ""),
                "pool_type": w.get("pool_type", "HOT"),
                "pro_score": float(tech.get("pro_score") or 0),
                "sm_score": float(tech.get("sm_score") or 1.0),
                "last_scan_time": last_scan,
                "created_at": tech.get("timestamp"),
                "orders": order_map.get(ticker, []),
                "t01_confirmed": tech.get("t01_confirmed", False),
                "t02_confirmed": tech.get("t02_confirmed", False),
                "t03_confirmed": tech.get("t03_confirmed", False),
                "t04_confirmed": tech.get("t04_confirmed", False),
                "movement_15m": tech.get("movement_15m"),
                "fib_zone_15m": tech.get("fib_zone_15m"),
                "movement_1d": tech.get("movement_1d"),
                "fib_zone_1d": tech.get("fib_zone_1d"),
                # Valuation data
                "composite_intrinsic": float(tech.get("intrinsic_value") or tech.get("intrinsic_price") or 0),
                "margin_of_safety": float(tech.get("margin_of_safety") or tech.get("undervaluation") or 0),
                "valuation_status": "undervalued" if tech.get("is_undervalued") else "fair_value",
                "data_source": "Engine V4.5",
                # Opportunity specific
                "entry_price": float(opp.get("entry_zone_high") or 0),
                "stop_loss": float(opp.get("stop_loss") or 0),
                "target_1": float(opp.get("target_1") or 0),
                "tp_block1_price": float(opp.get("target_1") or 0),
                "tp_block2_price": float(opp.get("target_2") or 0),
                "tp_block3_price": float(opp.get("target_3") or 0),
                "altman_z_score": float(tech.get("altman_z_score") or 0),
                "altman_zone": "safe" if float(tech.get("altman_z_score") or 0) > 2.9 else "distress",
                "graham_number": float(tech.get("graham_number") or 0),
                "dcf_intrinsic": float(tech.get("dcf_intrinsic") or 0),
                "ia_score": float(tech.get("ai_score") or 0),
                "math_score": float(tech.get("math_score") or 0),
                "analyst_rating": float(w.get("analyst_rating") or 0),
            }
            final_list.append(item)

        return {
            "opportunities": final_list,
            "total": len(final_list),
            "market_status": market_status
        }
    except Exception as e:
        log_error("stocks_api", f"Error in get_stocks_opportunities: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

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
