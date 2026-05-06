import asyncio
import os
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_positions_today():
    sb = get_supabase()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    res = sb.table("stocks_positions").select("*").gte("first_buy_at", today).execute()
    print(f"Positions opened today: {len(res.data)}")
    for pos in res.data:
        print(f"Ticker: {pos['ticker']}, Status: {pos['status']}, Entry: {pos['avg_price']}")

if __name__ == "__main__":
    asyncio.run(check_positions_today())
