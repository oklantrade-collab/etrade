import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.supabase_client import get_supabase

async def check_position():
    sb = get_supabase()
    # Search for the exact position
    res = sb.table("forex_positions").select("*").eq("symbol", "XAUUSD").execute()
    
    found = False
    if res.data:
        for p in res.data:
            if "Fallback" in str(p.get("close_reason")) or p.get("pnl_usd") == 1703.05 or "1703" in str(p.get("pnl_usd")):
                print("Found match in forex_positions:")
                print(p)
                found = True
    
    if not found:
        res2 = sb.table("positions").select("*").eq("symbol", "XAUUSD").execute()
        if res2.data:
            for p in res2.data:
                if "Fallback" in str(p.get("close_reason")) or p.get("pnl_usd") == 1703.05 or "1703" in str(p.get("pnl_usd")):
                    print("Found match in positions:")
                    print(p)

if __name__ == "__main__":
    asyncio.run(check_position())
