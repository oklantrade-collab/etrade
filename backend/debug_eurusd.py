import asyncio
from app.core.supabase_client import get_supabase

async def debug():
    sb = get_supabase()
    res = sb.table('market_candles').select('*').eq('symbol', 'EURUSD').order('open_time', desc=True).limit(5).execute()
    print("EURUSD CANDLES:")
    for c in res.data:
        print(f"Time: {c['open_time']}, O: {c['open']}, H: {c['high']}, L: {c['low']}, C: {c['close']}")

if __name__ == "__main__":
    asyncio.run(debug())
