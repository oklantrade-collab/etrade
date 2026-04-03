from app.core.supabase_client import get_supabase
import asyncio

async def check_candles():
    sb = get_supabase()
    res = sb.table('market_candles').select('symbol, timeframe, open_time, sar').eq('symbol', 'ADAUSDT').eq('timeframe', '4h').order('open_time', desc=True).limit(5).execute()
    print("Market Candles 4H SAR Check:")
    for row in res.data:
        print(f"Symbol: {row['symbol']}, Time: {row['open_time']}, SAR: {row['sar']}")

if __name__ == "__main__":
    asyncio.run(check_candles())
