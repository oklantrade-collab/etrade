import asyncio
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from app.workers.stocks_scheduler import get_stocks_config, get_watchlist, process_ticker

async def main():
    print("[ANALYSYS] Starting parallel analysis (17 tickers)...")
    config = get_stocks_config()
    tickers = await get_watchlist(config)
    
    if not tickers:
        print("No tickers found in watchlist.")
        return

    # Create tasks for all tickers
    tasks = [process_ticker(ticker, config) for ticker in tickers]
    
    # Run all tasks concurrently
    print(f"Downloading data and calculating indicators for {len(tickers)} stocks...")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    analyzed = 0
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            print(f"Error in {tickers[i]}: {res}")
        elif res:
            analyzed = analyzed + 1
            print(f"Done {tickers[i]}: Score={res['technical_score']} | Price={res['price']}")

    print(f"FINISHED! {analyzed} tickers updated in DB.")

if __name__ == "__main__":
    asyncio.run(main())
