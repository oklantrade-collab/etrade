import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_closed_forex_positions():
    sb = get_supabase()
    res = sb.table("positions").select("*").eq("market_type", "forex_futures").eq("status", "closed").order("closed_at", desc=True).limit(20).execute()
    for p in res.data:
        print(f"[{p['closed_at']}] {p['symbol']} {p['side']} Entry: {p['avg_entry_price']} Reason: {p['close_reason']} PnL: {p.get('realized_pnl')} Lotes: {p['size']}")

if __name__ == "__main__":
    asyncio.run(check_closed_forex_positions())
