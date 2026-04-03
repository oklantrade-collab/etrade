import asyncio
import pandas as pd
from app.execution.data_provider import BinanceCryptoProvider
from app.workers.scheduler import sync_current_candle_to_db, update_current_candle_close
from app.core.supabase_client import get_supabase
from app.core.config import settings
from app.core.memory_store import update_memory_df, MEMORY_STORE

async def debug_sync():
    print("Debugging candle sync...")
    prov = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    sb = get_supabase()
    
    df = await prov.get_ohlcv('BTC/USDT', '15m', limit=5)
    update_memory_df('BTCUSDT', '15m', df)
    
    last = df.iloc[-1]
    print(f"Last Candle Open Time: {last['open_time']} (type: {type(last['open_time'])})")
    
    ticker = await prov.get_ticker('BTC/USDT')
    price = ticker['price']
    
    # Run sync
    try:
        await sync_current_candle_to_db('BTCUSDT', price, sb)
        print("Sync function executed.")
    except Exception as e:
        print(f"Sync function FAILED: {e}")
    
    # Check what was sent
    timeframes_to_sync = ['15m']
    for tf in timeframes_to_sync:
        df_mem = MEMORY_STORE.get('BTCUSDT', {}).get(tf, {}).get('df', None)
        last_mem = df_mem.iloc[-1]
        ot = last_mem['open_time']
        if isinstance(ot, pd.Timestamp):
            ot = ot.isoformat()
        print(f"ISO Format used: {ot}")
        
    res = sb.table('market_candles').select('*').eq('symbol', 'BTC/USDT').eq('timeframe', '15m').order('open_time', desc=True).limit(5).execute()
    print("\nLATEST IN SUPABASE:")
    for r in res.data:
        print(f"{r['open_time']} | is_closed: {r['is_closed']} | close: {r['close']}")
        
    await prov.close()

if __name__ == "__main__":
    asyncio.run(debug_sync())
