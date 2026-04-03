import asyncio
from app.api.portfolio import get_performance_summary

async def test():
    try:
        print("Calling get_performance_summary...")
        res = await get_performance_summary()
        print("Result:", res)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test())
