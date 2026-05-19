import asyncio
import os
import sys
import json
from datetime import datetime, timezone, timedelta

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.supabase_client import get_supabase
from app.core.market_hours import is_market_open, get_nyc_now

async def debug_opportunities():
    print("Testing get_stocks_opportunities logic (post-fix)...")
    try:
        sb = get_supabase()
        
        is_open, status_text = is_market_open()
        print(f"Market Status: {is_open}, {status_text}")
        
        today_str = get_nyc_now().date().isoformat()
        
        print(f"Fetching technical_scores for {today_str}...")
        res_tech = sb.table("technical_scores")\
            .select("*")\
            .gte("timestamp", today_str)\
            .order("timestamp", desc=True)\
            .limit(200)\
            .execute()
        
        tech_data = res_tech.data or []
        print(f"Today's Technical scores count: {len(tech_data)}")

        if not tech_data:
            print("Weekend/Empty detected. Fetching last 3 days...")
            three_days_ago = (get_nyc_now() - timedelta(days=3)).date().isoformat()
            res_tech = sb.table("technical_scores")\
                .select("*")\
                .gte("timestamp", three_days_ago)\
                .order("timestamp", desc=True)\
                .limit(200)\
                .execute()
            tech_data = res_tech.data or []
            print(f"Fallback Technical scores count: {len(tech_data)}")
        
        print("Fetching watchlist_daily (WITHOUT margin_of_safety)...")
        wl_res = sb.table("watchlist_daily")\
            .select("ticker, pool_type, fundamental_score")\
            .eq("date", today_str)\
            .execute()
        wl_map = {r["ticker"]: r for r in (wl_res.data or [])}
        print(f"Watchlist Daily count: {len(wl_map)}")
        
        if not wl_map:
            print("Fallback for watchlist_daily...")
            wl_res = sb.table("watchlist_daily")\
                .select("ticker, pool_type, fundamental_score")\
                .order("date", desc=True)\
                .limit(100)\
                .execute()
            wl_map = {r["ticker"]: r for r in (wl_res.data or [])}
            print(f"Fallback Watchlist count: {len(wl_map)}")

        print("Logic seems OK. No crash.")
        
    except Exception as e:
        print(f"FAILED with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_opportunities())
