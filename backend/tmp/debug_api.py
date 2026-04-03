
import asyncio
import sys
import os
sys.path.append(os.getcwd())
from app.api.portfolio import get_global_portfolio

async def test():
    try:
        print("Starting get_global_portfolio()...")
        res = await get_global_portfolio()
        print("SUCCESS")
    except Exception as e:
        import traceback
        print("FAILED with:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
