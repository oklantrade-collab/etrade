import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def find_high_pnl():
    sb = get_supabase()
    # Check forex_positions
    res = sb.table('forex_positions').select('*').execute()
    high_forex = [p for p in res.data if p.get('pnl_usd') and abs(float(p['pnl_usd'])) > 10.0]
    print(f"High PNL in forex_positions: {len(high_forex)}")
    for p in high_forex:
        print(f"ID: {p['id']}, Symbol: {p['symbol']}, PNL: {p['pnl_usd']}")

    # Check positions
    res = sb.table('positions').select('*').execute()
    high_pos = [p for p in res.data if p.get('realized_pnl') and abs(float(p['realized_pnl'])) > 10.0]
    print(f"High PNL in positions: {len(high_pos)}")
    for p in high_pos:
        print(f"ID: {p['id']}, Symbol: {p['symbol']}, PNL: {p['realized_pnl']}")

if __name__ == "__main__":
    asyncio.run(find_high_pnl())
