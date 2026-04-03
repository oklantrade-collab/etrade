import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def dump_conds():
    sb = get_supabase()
    res = sb.table('strategy_conditions').select('id, name').execute()
    for r in res.data:
        print(f"{r['id']}: {r['name']}")
if __name__ == "__main__":
    asyncio.run(dump_conds())
