import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timezone, timedelta
from app.api.portfolio import get_global_portfolio, get_performance_summary

# Load env from parent
load_dotenv('.env')

async def test_api():
    print("Testing get_global_portfolio...")
    try:
        res = await get_global_portfolio()
        print("SUCCESS! Global keys:", res.keys())
    except Exception as e:
        print("FAILED get_global_portfolio:", e)
        import traceback
        traceback.print_exc()

    print("\nTesting get_performance_summary...")
    try:
        res = await get_performance_summary()
        print("SUCCESS! Performance keys:", res.keys())
    except Exception as e:
        print("FAILED get_performance_summary:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_api())
