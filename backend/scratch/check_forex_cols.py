import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_cols():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').limit(1).execute()
    if res.data:
        print(f"Columns in forex_positions: {list(res.data[0].keys())}")

if __name__ == "__main__":
    asyncio.run(check_cols())
