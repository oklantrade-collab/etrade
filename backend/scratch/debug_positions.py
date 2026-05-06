import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def debug_positions():
    sb = get_supabase()
    res = sb.table("positions").select("*").limit(5).execute()
    print("Data found:", len(res.data))
    if res.data:
        print("Keys:", res.data[0].keys())
        for r in res.data:
             print(f"Symbol: {r['symbol']}, MarketType: {r.get('market_type')}, Status: {r['status']}")

if __name__ == "__main__":
    asyncio.run(debug_positions())
