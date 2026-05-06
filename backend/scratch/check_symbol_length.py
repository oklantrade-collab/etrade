import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_symbol_length():
    sb = get_supabase()
    try:
        res = sb.table("positions").select("symbol").ilike("symbol", "%ADA%").limit(5).execute()
        for p in res.data:
            s = p['symbol']
            print(f"Symbol: '{s}' | Length: {len(s)}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_symbol_length())
