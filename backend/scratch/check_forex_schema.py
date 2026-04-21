import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_forex_schema():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').limit(1).execute()
    if res.data:
        print(json.dumps(res.data[0], indent=2))
    else:
        print("No rows in forex_positions.")

if __name__ == "__main__":
    asyncio.run(check_forex_schema())
