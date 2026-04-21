import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def list_active():
    sb = get_supabase()
    res = sb.table('forex_positions').select('symbol, status, pnl_usd').eq('status', 'active').execute()
    print(f"Active positions: {len(res.data)}")
    for p in res.data:
        print(p)

if __name__ == "__main__":
    asyncio.run(list_active())
