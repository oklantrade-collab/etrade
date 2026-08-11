import asyncio
from app.core.supabase_client import get_supabase

async def fetch_conds():
    sb = get_supabase()
    res = sb.table('strategy_conditions').select('id,name').ilike('name', '%SHORT HIGH OVER EMA20%').execute()
    for c in res.data:
        print(f"ID: {c['id']} | Name: {c['name']}")

if __name__ == '__main__':
    asyncio.run(fetch_conds())
