import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def check_pos():
    sb = get_supabase()
    pos = sb.table('positions').select('*').eq('symbol', 'BTCUSDT').execute().data
    print(json.dumps(pos, indent=2))
if __name__ == "__main__":
    asyncio.run(check_pos())
