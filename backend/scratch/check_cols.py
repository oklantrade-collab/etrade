import asyncio
import os
import sys
import json

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.supabase_client import get_supabase

async def check_columns():
    sb = get_supabase()
    print("Checking watchlist_daily columns...")
    try:
        # Fetch one record to see keys
        res = sb.table("watchlist_daily").select("*").limit(1).execute()
        if res.data:
            print("Columns found in watchlist_daily:")
            print(list(res.data[0].keys()))
        else:
            print("No data in watchlist_daily, trying to fetch from tech_scores...")
            res = sb.table("technical_scores").select("*").limit(1).execute()
            if res.data:
                print("Columns found in technical_scores:")
                print(list(res.data[0].keys()))
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_columns())
