import asyncio
import os
import sys
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.supabase_client import get_supabase

async def check_columns():
    sb = get_supabase()
    print("Checking market_snapshot columns...")
    try:
        # Fetch one record to see keys
        res = sb.table("market_snapshot").select("*").limit(1).execute()
        if res.data:
            print("Columns found in market_snapshot:")
            print(list(res.data[0].keys()))
        else:
            print("No data in market_snapshot.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_columns())
