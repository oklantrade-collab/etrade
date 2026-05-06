import asyncio
import os
import sys
from app.core.supabase_client import get_supabase

async def check_columns():
    sb = get_supabase()
    try:
        # Get one row to see columns
        res = sb.table('market_snapshot').select('*').limit(1).execute()
        if res.data:
            print("Columns in market_snapshot:")
            for key in res.data[0].keys():
                print(f" - {key}")
        else:
            print("No data in market_snapshot to check columns.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_columns())
