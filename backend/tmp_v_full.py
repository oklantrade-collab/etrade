import asyncio, json
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    v = sb.table('strategy_variables').select('*').execute()
    c = sb.table('strategy_conditions').select('*').execute()
    r = sb.table('strategy_rules_v2').select('*').execute()
    print("VARS:")
    for row in v.data: print(f"ID:{row['id']} Code:{row['source_field']} Name:{row['name']}")
    print("CONDS:")
    for row in c.data: print(f"ID:{row['id']} VarID:{row.get('variable_id')} Name:{row['name']}")
    print("RULES:")
    for row in r.data: print(f"ID:{row['id']} Code:{row['rule_code']} Weights:{row['condition_weights']}")

if __name__ == "__main__":
    asyncio.run(check())
