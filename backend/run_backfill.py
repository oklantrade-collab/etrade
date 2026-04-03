import asyncio
import os
import sys

# Add path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.workers.scheduler import backfill_candles

async def main():
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT']
    for sym in symbols:
        print(f"Starting backfill for {sym}...")
        await backfill_candles(sym, bars=300)
        print(f"Finished {sym}")

if __name__ == "__main__":
    asyncio.run(main())
