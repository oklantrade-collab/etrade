import asyncio
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
load_dotenv('backend/.env')

from app.core.supabase_client import get_supabase

async def check_all():
    sb = get_supabase()
    tables = ["watchlist_daily", "technical_scores", "market_snapshot"]
    
    for table in tables:
        print(f"\n--- Table: {table} ---")
        try:
            res = sb.table(table).select("*").limit(1).execute()
            if res.data:
                print(f"Columns: {list(res.data[0].keys())}")
            else:
                print("No data in table.")
        except Exception as e:
            print(f"Error checking {table}: {e}")

if __name__ == "__main__":
    asyncio.run(check_all())
