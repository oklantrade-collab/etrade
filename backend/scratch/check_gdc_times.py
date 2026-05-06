import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_gdc_times():
    sb = get_supabase()
    res = sb.table("stocks_positions").select("first_buy_at, entry_time").eq("ticker", "GDC").execute()
    if res.data:
        for pos in res.data:
            print(f"first_buy_at: {pos['first_buy_at']} | entry_time: {pos['entry_time']}")
    else:
        print("No GDC positions found")

if __name__ == "__main__":
    asyncio.run(check_gdc_times())
