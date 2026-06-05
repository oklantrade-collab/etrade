import asyncio
from app.core.supabase_client import get_supabase

async def check_conds():
    sb = get_supabase()
    res = sb.table('strategy_conditions').select('name, id, variable_id, operator, value_variable').execute()
    for row in res.data:
        print(f"{row['id']}: {row['name']} (var_id={row['variable_id']} op={row['operator']} val_var={row['value_variable']})")

asyncio.run(check_conds())
