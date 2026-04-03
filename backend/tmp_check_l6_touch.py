import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def check_lows():
    sb = get_supabase()
    res = sb.table('market_candles').select('open_time, low, lower_6').eq('symbol', 'BTCUSDT').eq('timeframe', '15m').order('open_time', desc=True).limit(25).execute()
    for c in res.data:
        is_touch = float(c['low']) <= float(c['lower_6'])
        print(f"Time: {c['open_time']} | Low: {c['low']} | L6: {c['lower_6']} | Touch: {is_touch}")
if __name__ == "__main__":
    asyncio.run(check_lows())
