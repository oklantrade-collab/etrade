from app.api.stocks import get_stocks_positions
import asyncio

async def test_api():
    res = await get_stocks_positions()
    print(f"POSITIONS COUNT: {len(res.get('positions', []))}")
    if 'error' in res:
        print(f"ERROR: {res['error']}")
    for p in res.get('positions', []):
        print(f"{p['ticker']} | {p['status']}")

if __name__ == "__main__":
    asyncio.run(test_api())
