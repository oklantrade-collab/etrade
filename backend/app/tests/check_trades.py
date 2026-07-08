import sys
import os
import asyncio
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.core.supabase_client import get_supabase

async def check_trades():
    sb = get_supabase()
    res = sb.table("stocks_positions").select("*").eq("status", "closed").order("created_at", desc=True).limit(5).execute()
    print("Ultimas 5 posiciones cerradas:")
    for p in res.data:
        print(f"ID: {p['id']}, Ticker: {p['ticker']}, Created: {p.get('created_at')}, PNL: {p.get('realized_pnl')}")

if __name__ == "__main__":
    asyncio.run(check_trades())
