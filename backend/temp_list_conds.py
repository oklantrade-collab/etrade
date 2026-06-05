import asyncio
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    
    res_vars = sb.table('strategy_variables').select('id, name, source_field').execute()
    print('Variables:')
    for v in res_vars.data:
        print(f"  {v['id']}: {v['name']} ({v['source_field']})")

    res_conds = sb.table('strategy_conditions').select('id, name').execute()
    print('Conditions:')
    for c in res_conds.data:
        print(f"  {c['id']}: {c['name']}")

asyncio.run(check())
