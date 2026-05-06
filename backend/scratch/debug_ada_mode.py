import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def debug_positions_mode():
    sb = get_supabase()
    try:
        res = sb.table("positions").select("*").ilike("symbol", "%ADA%").eq("status", "open").execute()
        for p in res.data:
            print(f"ID: {p['id']} | Mode: {p.get('mode')} | Status: {p['status']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_positions_mode())
