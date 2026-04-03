import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def check_cond():
    sb = get_supabase()
    res = sb.table('strategy_conditions').select('*').eq('id', 59).maybe_single().execute()
    print(json.dumps(res.data, indent=2))
if __name__ == "__main__":
    asyncio.run(check_cond())
