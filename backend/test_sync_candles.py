import asyncio
import pandas as pd
from app.execution.data_provider import BinanceCryptoProvider
from app.analysis.indicators_v2 import calculate_all_indicators
from app.workers.scheduler import sync_current_candle_to_db, update_current_candle_close
from app.core.supabase_client import get_supabase
from app.core.config import settings
from app.core.memory_store import update_memory_df

async def test_candle_sync():
    print("Running manual candle sync for BTCUSDT...")
    prov = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    sb = get_supabase()
    
    # 1. Fetch 15m and update memory
    df = await prov.get_ohlcv('BTC/USDT', '15m', limit=100)
    df = calculate_all_indicators(df, {})
    update_memory_df('BTCUSDT', '15m', df)
    
    # 2. Get current price
    ticker = await prov.get_ticker('BTC/USDT')
    current_price = ticker['price']
    
    # 3. Update memory with current price
    update_current_candle_close('BTCUSDT', current_price)
    
    # 4. Sync to DB
    await sync_current_candle_to_db('BTCUSDT', current_price, sb)
    
    print("Sync complete. Verifying Supabase...")
    res = sb.table('market_candles').select('symbol, timeframe, open_time, close, is_closed').eq('symbol', 'BTC/USDT').eq('timeframe', '15m').order('open_time', desc=True).limit(3).execute()
    print("CHECK 1 (15m):")
    for r in res.data:
        print(r)
        
    res4h = sb.table('market_candles').select('symbol, timeframe, open_time, close, is_closed').eq('symbol', 'BTC/USDT').eq('timeframe', '4h').order('open_time', desc=True).limit(2).execute()
    print("\nCHECK 3 (4h) - results might be empty if 4h not in memory:")
    for r in res4h.data:
        print(r)
        
    await prov.close()

if __name__ == "__main__":
    asyncio.run(test_candle_sync())
