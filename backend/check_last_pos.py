import asyncio
import os
import sys
from app.core.supabase_client import get_supabase

async def check_positions():
    sb = get_supabase()
    try:
        res = sb.table('forex_positions').select('*').order('opened_at', desc=True).limit(5).execute()
        print("Last 5 positions:")
        for p in res.data:
            print(f"ID: {p['id']}, Symbol: {p['symbol']}, Side: {p['side']}, Entry: {p['entry_price']}, Lots: {p['lots']}, Status: {p['status']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_positions())
