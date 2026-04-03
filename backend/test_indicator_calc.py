import asyncio
import os
import sys
import pandas as pd

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.execution.data_provider import BinanceCryptoProvider
from app.analysis.indicators_v2 import calculate_all_indicators
from app.core.config import settings

async def check_calcs():
    provider = BinanceCryptoProvider(settings.binance_api_key, settings.binance_secret)
    df_raw = await provider.get_ohlcv('BTCUSDT', '4h', limit=500)
    print(f"Fetched {len(df_raw)} candles")
    
    df = calculate_all_indicators(df_raw, {})
    print(f"Calculated indicators for {len(df)} candles")
    
    # Check basis in the tail
    print("\nTail indicators:")
    print(df[['open_time', 'close', 'basis', 'upper_6']].tail(10))
    
    # Check if basis is 0 anywhere in the last 100 rows
    zeros = df.tail(100)[df.tail(100)['basis'] <= 0]
    print(f"\nRows with basis <= 0 in last 100: {len(zeros)}")
    
    await provider.close()

if __name__ == "__main__":
    asyncio.run(check_calcs())
