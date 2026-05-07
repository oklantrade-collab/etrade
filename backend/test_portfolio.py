import asyncio
import os
import sys

# Set up path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.api.portfolio import get_performance_summary

async def test():
    try:
        res = await get_performance_summary()
        print("OK")
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(test())
