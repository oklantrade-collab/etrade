import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_high_pnl():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').gte('pnl_usd', 1000).execute()
    print(f"Trades with PnL > 1000: {len(res.data or [])}")
    for p in res.data:
        print(f"Symbol: {p['symbol']}, ID: {p['id']}, PnL: {p['pnl_usd']}, Entry: {p['entry_price']}, Status: {p['status']}")

if __name__ == "__main__":
    asyncio.run(check_high_pnl())
