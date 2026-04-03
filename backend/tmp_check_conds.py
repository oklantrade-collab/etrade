from app.core.supabase_client import get_supabase
import asyncio

async def check_conds():
    sb = get_supabase()
    res = sb.table('strategy_conditions').select('*').eq('variable_id', 23).execute() # 23 is fibonacci_zone
    for c in res.data:
        print(f"ID: {c['id']}, Name: {c['name']}, Op: {c['operator']}, Val: {c['value_literal']}")

if __name__ == "__main__":
    asyncio.run(check_conds())
