import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.execution.provider_factory import create_provider
from app.analysis.indicators_v2 import calculate_all_indicators

async def debug():
    provider_crypto = create_provider('crypto_futures')
    df = await provider_crypto.get_ohlcv('BTCUSDT', '5m', limit=200)
    df = calculate_all_indicators(df, {})
    
    crosses = 0
    for i in range(len(df)-96, len(df)):
        if i < 1: continue
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        # Check condition
        cruce_up = (row['ema1'] > row['ema2']) and (prev['ema1'] <= prev['ema2'])
        sec_cond = (row['ema2'] > row['ema3']) or (row['ema1'] > row['ema3'])
        
        if cruce_up:
            print(f"Cruce normal detectado en índice {i}. sec_cond={sec_cond}")
            crosses += 1
            
    print(f"Total cruces detectados: {crosses}")

if __name__ == '__main__':
    asyncio.run(debug())
