import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.api.stocks import get_stocks_opportunities

async def test_api():
    try:
        res = await get_stocks_opportunities()
        print("API finished successfully.")
        print("Keys returned:", res.keys())
        print("Total opportunities:", res.get("total"))
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_api())
