import asyncio
import os
import sys
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    from datetime import datetime
    today = datetime.now().date().isoformat()
    res = sb.table("watchlist_daily").select("ticker", count="exact").eq("date", today).eq("hard_filter_pass", True).execute()
    print(f"Watchlist tickers for today: {res.count}")

if __name__ == "__main__":
    asyncio.run(check())
