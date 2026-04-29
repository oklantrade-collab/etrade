import asyncio
import os
import sys
from datetime import date

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_watchlist():
    sb = get_supabase()
    today = date.today().isoformat()
    res = sb.table('watchlist_daily').select('ticker, pool_type, fundamental_score').eq('date', today).limit(20).execute()
    print(f"--- WATCHLIST DAILY ({today}) ---")
    for r in res.data:
        print(f"{r['ticker']} | Pool: {r['pool_type']} | Score: {r['fundamental_score']}")

if __name__ == "__main__":
    asyncio.run(check_watchlist())
