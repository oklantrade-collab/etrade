import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def check_xau_detailed():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').execute()
    print(f"XAUUSD found: {len(res.data)}")
    for p in res.data:
        print(f"ID: {p['id']}, Lots: {p.get('lots')}, PNL_USD: {p.get('pnl_usd')}, Pips_PNL: {p.get('pips_pnl')}, Price: {p.get('entry_price')} -> {p.get('current_price') or p.get('exit_price')}")

if __name__ == "__main__":
    asyncio.run(check_xau_detailed())
