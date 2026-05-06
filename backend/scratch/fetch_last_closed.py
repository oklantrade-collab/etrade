import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def fetch_last_closed():
    sb = get_supabase()
    res = sb.table("positions").select("*").eq("status", "closed").order("closed_at", desc=True).limit(100).execute()
    for p in res.data:
        sym = p['symbol']
        if any(x in sym for x in ["EUR", "GBP", "USD", "JPY", "XAU"]):
             print(f"[{p['closed_at']}] {p['symbol']} {p['side']} Entry: {p['avg_entry_price']} Reason: {p['close_reason']} PnL: {p.get('realized_pnl')}")

if __name__ == "__main__":
    asyncio.run(fetch_last_closed())
