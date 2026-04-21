import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def get_columns():
    sb = get_supabase()
    res = sb.table('positions').select('*').limit(1).execute()
    if res.data:
        print("Columns: " + ", ".join(res.data[0].keys()))
    else:
        print("No data.")

if __name__ == "__main__":
    asyncio.run(get_columns())
