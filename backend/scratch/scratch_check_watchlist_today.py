import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from datetime import date
from app.core.supabase_client import get_supabase

async def check_watchlist_today():
    sys.stdout.reconfigure(encoding='utf-8')
    sb = get_supabase()
    today = date.today().isoformat()
    
    print(f"=== WATCHLIST FOR TODAY ({today}) ===")
    res_today = sb.table("watchlist_daily").select("*").eq("date", today).execute()
    data_today = res_today.data or []
    print(f"Total entries in watchlist_daily for today: {len(data_today)}")
    
    if data_today:
        print("\n--- SAMPLES OF TODAY'S WATCHLIST ---")
        for r in data_today[:10]:
            print(f"  Ticker: {r.get('ticker'):<6} | Hard Filter Pass: {r.get('hard_filter_pass')} | Catalyst Score: {r.get('catalyst_score')} | Pool: {r.get('pool_type')}")
            
        print("\n--- TICKERS THAT PASSED HARD FILTER TODAY ---")
        passed = [r for r in data_today if r.get('hard_filter_pass') == True]
        print(f"  Count: {len(passed)}")
        for r in passed:
            print(f"    - {r.get('ticker')} (Catalyst: {r.get('catalyst_score')}, Pool: {r.get('pool_type')})")
            
    else:
        print("No watchlist entries found for today in watchlist_daily.")
        
    # Check what was the last date populated in watchlist_daily
    print("\n=== RECENT DATES IN WATCHLIST_DAILY ===")
    res_recent = sb.table("watchlist_daily").select("date").order("date", desc=True).limit(20).execute()
    recent_dates = sorted(list(set(r.get('date') for r in (res_recent.data or []))), reverse=True)
    print(f"Recent dates with data: {recent_dates}")

if __name__ == "__main__":
    asyncio.run(check_watchlist_today())
