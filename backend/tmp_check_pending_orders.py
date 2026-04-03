import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def check_pending():
    sb = get_supabase()
    res = sb.table('pending_orders').select('*').eq('symbol', 'BTCUSDT').execute()
    for o in res.data:
        print(f"ID: {o['id']} | Rule: {o['rule_code']} | Status: {o['status']} | Limit: {o['limit_price']}")
if __name__ == "__main__":
    asyncio.run(check_pending())
