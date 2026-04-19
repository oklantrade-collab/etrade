import asyncio
import os
import sys
from datetime import datetime

# Add root to path
sys.path.append(os.getcwd())

from backend.app.workers.stocks_scheduler import process_ticker, get_stocks_config, get_watchlist

async def force_full_scan():
    print(f"[{datetime.now()}] Starting FORCED full scan...")
    config = get_stocks_config()
    tickers = await get_watchlist(config)
    
    if not tickers:
        print("No tickers in watchlist.")
        return

    print(f"Analysis for {len(tickers[:30])} tickers...")
    tasks = [process_ticker(t, config) for t in tickers[:30]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success = 0
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            print(f"Error {tickers[i]}: {res}")
        elif res:
            success += 1
            print(f"Done: {tickers[i]}")
            
    print(f"Full scan finished. {success} tickers updated.")

if __name__ == "__main__":
    asyncio.run(force_full_scan())
