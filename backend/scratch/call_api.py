import sys
import os
import asyncio
import httpx

async def check_api():
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("http://localhost:8000/api/v1/stocks/opportunities", timeout=10.0)
            print("Status code:", res.status_code)
            data = res.json()
            print("Response keys:", data.keys())
            print(f"Total opportunities returned: {len(data.get('opportunities', []))}")
    except Exception as e:
        print("Error calling API:", e)

if __name__ == "__main__":
    asyncio.run(check_api())
