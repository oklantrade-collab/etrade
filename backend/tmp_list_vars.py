import asyncio
from app.core.supabase_client import get_supabase

async def list_v():
    sb = get_supabase()
    res = sb.table('strategy_variables').select('*').execute()
    print(res.data)

if __name__ == "__main__":
    asyncio.run(list_v())
