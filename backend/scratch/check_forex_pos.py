import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_forex_positions_table():
    sb = get_supabase()
    try:
        res = sb.table("forex_positions").select("*").order("opened_at", desc=True).limit(20).execute()
        for p in res.data:
            print(f"[{p.get('closed_at', 'OPEN')}] {p['symbol']} {p['side']} Entry: {p['avg_entry_price']} Reason: {p.get('close_reason')} PnL: {p.get('realized_pnl')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_forex_positions_table())
