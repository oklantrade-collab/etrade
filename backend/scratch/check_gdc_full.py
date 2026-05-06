import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_gdc_full():
    sb = get_supabase()
    res = sb.table("stocks_positions").select("*").eq("ticker", "GDC").eq("status", "closed").execute()
    if res.data:
        pos = res.data[-1]
        for k, v in pos.items():
            if v is not None and v != 0 and v != "":
                print(f"{k}: {v}")
    else:
        print("GDC closed positions not found")

if __name__ == "__main__":
    asyncio.run(check_gdc_full())
