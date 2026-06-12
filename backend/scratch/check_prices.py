import asyncio
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.execution.data_provider import get_ticker

async def test_ticker():
    res = await get_ticker("XAUUSD", "forex_futures")
    print("XAUUSD:", res)

    res2 = await get_ticker("EURUSD", "forex_futures")
    print("EURUSD:", res2)

    res3 = await get_ticker("US500", "forex_futures")
    print("US500:", res3)

if __name__ == "__main__":
    asyncio.run(test_ticker())
