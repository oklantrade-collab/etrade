import asyncio
import pandas as pd
from app.execution.data_provider import BinanceCryptoProvider
from app.analysis.indicators_v2 import calculate_all_indicators
from app.core.config import settings

async def test():
    print("Testing indicators calculation...")
    prov = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    df = await prov.get_ohlcv('BTC/USDT', '15m', limit=300)
    df = calculate_all_indicators(df, {})
    last = df.iloc[-1]
    
    print(f"Basis: {last.get('basis')}")
    for i in range(1, 7):
        print(f"Upper_{i}: {last.get(f'upper_{i}')}")
    
    await prov.close()

if __name__ == "__main__":
    asyncio.run(test())
