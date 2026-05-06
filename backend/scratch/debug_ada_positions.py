import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def debug_positions():
    sb = get_supabase()
    try:
        # Get ALL positions for ADAUSDT
        res = sb.table("positions").select("*").ilike("symbol", "%ADA%").execute()
        print(f"Total positions found for ADA: {len(res.data)}")
        for p in res.data:
            print(f"ID: {p['id']} | Status: '{p['status']}' | Opened: {p['opened_at']} | Rule: {p['rule_code']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_positions())
