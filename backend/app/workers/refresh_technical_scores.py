import asyncio
import os
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))
sys.path.append(backend_dir)
os.chdir(backend_dir)  # Change to backend root for consistent imports

from dotenv import load_dotenv
load_dotenv(".env")

from app.workers.stocks_scheduler import process_ticker, get_stocks_config, get_watchlist

async def refresh_all():
    cfg = get_stocks_config()
    tickers = await get_watchlist(cfg)
    print(f"Refreshing top {min(len(tickers), 30)} tickers...")
    
    # Process in chunks of 5 to avoid overloading
    chunk_size = 5
    for i in range(0, min(len(tickers), 30), chunk_size):
        chunk = tickers[i:i+chunk_size]
        print(f"Processing chunk: {chunk}")
        tasks = [process_ticker(t, cfg) for t in chunk]
        await asyncio.gather(*tasks)
    
    print("Refresh completed successfully.")

if __name__ == "__main__":
    asyncio.run(refresh_all())
