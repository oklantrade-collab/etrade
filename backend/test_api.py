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
            print(f"FIRST TICKER: {res['opportunities'][0]['ticker']}")
    except Exception as e:
        print(f"ERROR: {e}")

asyncio.run(test())
