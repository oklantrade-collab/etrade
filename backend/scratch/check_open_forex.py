import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_open_forex():
    sb = get_supabase()
    try:
        res = sb.table("forex_positions").select("*").eq("status", "open").execute()
        print(f"Found {len(res.data)} OPEN Forex positions.")
        for p in res.data:
            print(f"[{p['opened_at']}] {p['symbol']} {p['side']} Entry: {p['entry_price']} Lots: {p['lots']} Rule: {p.get('rule_code')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_open_forex())
