import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_snaps():
    sb = get_supabase()
    res = sb.table('market_snapshot').select('symbol').execute()
    symbols = sorted([r['symbol'] for r in res.data])
    print(f"Symbols in snapshot: {symbols}")

if __name__ == "__main__":
    asyncio.run(check_snaps())
