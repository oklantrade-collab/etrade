from app.core.supabase_client import get_supabase
import asyncio

async def check_vars_start():
    sb = get_supabase()
    res = sb.table('strategy_variables').select('*').order('id').limit(30).execute()
    for v in res.data:
        print(f"ID: {v['id']}, Name: {v['name']}, Source: {v['source_field']}")

if __name__ == "__main__":
    asyncio.run(check_vars_start())
