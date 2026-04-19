import asyncio
from app.api.stocks import get_stocks_opportunities
from app.core.supabase_client import get_supabase
import json

async def test():
    try:
        sb = get_supabase()
        res = await get_stocks_opportunities(sb=sb)
        print(f"TOTAL: {res['total']}")
        if res['total'] > 0:
            for o in res['opportunities']:
                print(f"TICKER: {o['ticker']} | RVOL: {o['rvol']} | PRO: {o['is_pro_member']} | VOL: {o['volume']}")
    except Exception as e:
        print(f"ERROR: {e}")

asyncio.run(test())
