import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase
async def check_4h():
    sb = get_supabase()
    res = sb.table('market_candles').select('open_time, close, lower_6').eq('symbol', 'BTCUSDT').eq('timeframe', '4h').order('open_time', desc=True).limit(5).execute()
    for c in res.data:
        print(f"Time: {c['open_time']} | Close: {c['close']} | L6: {c['lower_6']}")
if __name__ == "__main__":
    asyncio.run(check_4h())
