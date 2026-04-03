import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from app.workers.scheduler import backfill_candles

async def main():
    sb = get_supabase()
    # Get active symbols from config
    res = sb.table('trading_config').select('active_symbols').eq('id', 1).maybe_single().execute()
    symbols = res.data.get('active_symbols') if res.data else ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]
    
    # Standardize format (Standardization rule: No slash, BTCUSDT)
    symbols = [s.replace('/', '') for s in symbols]
    
    print(f"Backfilling indicators for: {symbols}")
    
    for symbol in symbols:
        print(f"[{symbol}] Processing backfill (500 bars)...")
        # Increase bars to 500 to ensure indicators calculate correctly (need 200)
        # And since upsert limit is 300, we'll have 300 fully populated candles.
        await backfill_candles(symbol, bars=500, sb=sb)
    
    print("Done.")

if __name__ == "__main__":
    asyncio.run(main())
