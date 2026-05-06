import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_forex_positions_v2():
    sb = get_supabase()
    try:
        res = sb.table("forex_positions").select("*").order("opened_at", desc=True).limit(50).execute()
        for p in res.data:
            entry = p.get('avg_entry_price') or p.get('entry_price') or 'N/A'
            print(f"[{p.get('closed_at', 'OPEN')}] {p['symbol']} {p['side']} Entry: {entry} Reason: {p.get('close_reason')} PnL: {p.get('realized_pnl')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_forex_positions_v2())
