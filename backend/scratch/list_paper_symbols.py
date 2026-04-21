import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def list_paper():
    sb = get_supabase()
    res = sb.table('paper_trades').select('symbol, total_pnl_usd').execute()
    print(f"Total paper trades: {len(res.data)}")
    symbols = set(p['symbol'] for p in res.data)
    print(f"Symbols: {symbols}")

if __name__ == "__main__":
    asyncio.run(list_paper())
