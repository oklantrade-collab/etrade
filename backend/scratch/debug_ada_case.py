import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def debug_ada_case():
    sb = get_supabase()
    try:
        res = sb.table("positions").select("symbol").ilike("symbol", "%ADA%").limit(1).execute()
        if res.data:
            print(f"Symbol in DB: '{res.data[0]['symbol']}'")
        else:
            print("No ADA positions found.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_ada_case())
