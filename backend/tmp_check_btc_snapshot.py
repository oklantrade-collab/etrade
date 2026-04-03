import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def check_snap():
    sb = get_supabase()
    res = sb.table('market_snapshot').select('symbol, price, fibonacci_zone, updated_at').eq('symbol', 'BTCUSDT').execute()
    print(json.dumps(res.data, indent=2))
if __name__ == "__main__":
    asyncio.run(check_snap())
