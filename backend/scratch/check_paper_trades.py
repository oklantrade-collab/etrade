import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_paper_trades():
    sb = get_supabase()
    res = sb.table('paper_trades').select('symbol, total_pnl_usd').ilike('symbol', '%XAU%').execute()
    print(f"XAU related paper trades: {len(res.data)}")
    for p in res.data[:10]:
        print(p)

if __name__ == "__main__":
    asyncio.run(check_paper_trades())
