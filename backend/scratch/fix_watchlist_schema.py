import asyncio
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
load_dotenv('backend/.env')

from app.core.supabase_client import get_supabase

async def fix_watchlist_schema():
    sb = get_supabase()
    print("Fixing watchlist_daily schema...")
    
    queries = [
        "ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS margin_of_safety NUMERIC DEFAULT 0;",
        "ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS intrinsic_value NUMERIC DEFAULT 0;",
        "ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS is_overvalued BOOLEAN DEFAULT false;",
        "ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS analyst_rating NUMERIC DEFAULT 0;",
    ]
    
    for i, query in enumerate(queries):
        try:
            print(f"Executing: {query}")
            # Try different param names for exec_sql
            try:
                sb.rpc('exec_sql', {'sql_query': query}).execute()
            except:
                sb.rpc('exec_sql', {'query': query}).execute()
            print(f"  OK.")
        except Exception as e:
            print(f"  FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(fix_watchlist_schema())
