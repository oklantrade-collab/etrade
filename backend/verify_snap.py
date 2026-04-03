from app.core.supabase_client import get_supabase
import asyncio

async def check():
    sb = get_supabase()
    res = sb.table('market_snapshot').select('symbol, sar_phase, sar_trend_4h, sar_4h').execute()
    print("Market Snapshot SAR Check:")
    for row in res.data:
        print(f"Symbol: {row['symbol']}, Phase: {row['sar_phase']}, Trend: {row['sar_trend_4h']}, SAR: {row['sar_4h']}")

if __name__ == "__main__":
    asyncio.run(check())
