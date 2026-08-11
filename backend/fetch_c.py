import asyncio
from app.core.supabase_client import get_supabase

async def fetch_conds():
    sb = get_supabase()
    cond_ids = [12, 37, 47, 214, 215, 218, 226]
    cond_res = sb.table('strategy_conditions').select('id,name').in_('id', cond_ids).execute()
    for c in cond_res.data:
        print(f"ID: {c['id']} | Name: {c['name']}")

if __name__ == '__main__':
    asyncio.run(fetch_conds())
