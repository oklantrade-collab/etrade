import asyncio
from app.core.supabase_client import get_supabase

async def debug():
    sb = get_supabase()
    res = sb.table('market_snapshot').select('*').limit(1).execute()
    if res.data:
        print("COLUMNS:", res.data[0].keys())

if __name__ == "__main__":
    asyncio.run(debug())
