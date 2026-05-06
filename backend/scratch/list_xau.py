import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def list_xau():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').execute()
    print(f"Active Forex Positions for XAUUSD: {len(res.data or [])}")
    for p in res.data:
        print(f"ID: {p['id']}, Entry: {p['entry_price']}, Status: {p['status']}")
    
    # Also check 'positions' table (might be the old one)
    res2 = sb.table('positions').select('*').eq('symbol', 'XAUUSD').execute()
    print(f"Old Positions for XAUUSD: {len(res2.data or [])}")
    for p in res2.data:
        print(f"ID: {p['id']}, Entry: {p.get('entry_price') or p.get('avg_entry_price')}, Status: {p['status']}")

if __name__ == "__main__":
    asyncio.run(list_xau())
