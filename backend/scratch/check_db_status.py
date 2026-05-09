import asyncio
import os
from app.core.supabase_client import get_supabase

async def check_scores():
    sb = get_supabase()
    res = sb.table("technical_scores").select("ticker, timestamp").order("timestamp", desc=True).limit(5).execute()
    print(f"RECENT SCORES: {res.data}")
    
    res_snap = sb.table("market_snapshot").select("symbol, price, apex_4h").limit(5).execute()
    print(f"SNAPSHOTS: {res_snap.data}")

if __name__ == "__main__":
    asyncio.run(check_scores())
