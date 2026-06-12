import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.execution.provider_factory import create_provider

async def test():
    print("Testing provider...", flush=True)
    provider = create_provider('crypto_futures')
    print("Provider created.", flush=True)
    df = await provider.get_ohlcv('BTCUSDT', '5m', limit=10)
    print("DF fetched.", flush=True)
    print(df, flush=True)
    await provider.close()

if __name__ == '__main__':
    asyncio.run(test())
