import asyncio
import os
import sys
from datetime import datetime, timedelta

# Add backend to path
sys.path.append(os.getcwd())

from app.core.supabase_client import get_supabase

async def test_api_logic():
    print("Testing API Opportunities Logic...")
    sb = get_supabase()
    
    # Simulate parts of get_stocks_opportunities
    try:
        from datetime import date
        today = date.today().isoformat()
        
        # 1. Get Watchlist
        wl = sb.table("watchlist_daily")\
            .select("*")\
            .eq("date", today)\
            .execute()
        
        print(f"Watchlist items for today ({today}): {len(wl.data) if wl.data else 0}")
        
        # 2. Get Tech Scores
        tech_res = sb.table("technical_scores")\
            .select("*")\
            .order("timestamp", desc=True)\
            .execute()
        
        if tech_res.data:
            t = tech_res.data[0]
            print(f"Latest timestamp: {t.get('timestamp')}")
            
            # Test formatting logic
            try:
                ts_str = t["timestamp"].replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts_str)
                lima_time = (dt - timedelta(hours=5)).strftime("%H:%M")
                print(f"Lima time formatted: {lima_time}")
            except Exception as e:
                print(f"Formatting failed: {e}")
        else:
            print("No technical scores found at all.")

    except Exception as e:
        print(f"API Simulation failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_api_logic())
