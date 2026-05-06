import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.workers.stocks_scheduler import run_stocks_cycle

async def force_cycle():
    print("Forcing Stocks Cycle...")
    await run_stocks_cycle(force=True)
    print("Cycle finished.")

if __name__ == "__main__":
    asyncio.run(force_cycle())
