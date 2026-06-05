import asyncio
from app.core.supabase_client import get_supabase

async def check_vars():
    sb = get_supabase()
    res = sb.table('strategy_variables').select('*').execute()
    for row in res.data:
        print(f"{row['id']}: {row['name']} ({row['source_field']})")

asyncio.run(check_vars())
