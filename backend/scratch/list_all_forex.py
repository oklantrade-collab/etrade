import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def list_all_forex():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').execute()
    print(f"Total Forex Positions: {len(res.data or [])}")
    for p in res.data:
        print(f"Symbol: {p['symbol']}, ID: {p['id']}, Entry: {p['entry_price']}, Status: {p['status']}")

if __name__ == "__main__":
    asyncio.run(list_all_forex())
