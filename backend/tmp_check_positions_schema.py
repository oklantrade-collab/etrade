from app.core.supabase_client import get_supabase
import asyncio

async def check_positions_schema():
    sb = get_supabase()
    res = sb.table('positions').select('*').limit(1).execute()
    print(res.data[0].keys())

if __name__ == "__main__":
    asyncio.run(check_positions_schema())
