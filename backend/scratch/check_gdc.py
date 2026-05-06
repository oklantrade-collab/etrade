import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_gdc():
    sb = get_supabase()
    res = sb.table("stocks_positions").select("*").eq("ticker", "GDC").eq("status", "closed").execute()
    if res.data:
        pos = res.data[-1] # Get last one
        print(f"Ticker: {pos['ticker']}")
        print(f"Status: {pos['status']}")
        print(f"Close Reason: {pos.get('sl_close_reason')}")
        print(f"Rule Code: {pos.get('rule_code')}")
        print(f"Entry: {pos['avg_price']}, Exit: {pos.get('current_price')}")
    else:
        print("GDC closed positions not found")

if __name__ == "__main__":
    asyncio.run(check_gdc())
