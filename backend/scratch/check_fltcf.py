import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_fltcf():
    sb = get_supabase()
    res = sb.table("technical_scores").select("*").eq("ticker", "FLTCF").execute()
    if res.data:
        print(f"Ticker: {res.data[0]['ticker']}, Score: {res.data[0]['technical_score']}")
        print(f"Sigs: {res.data[0]['signals_json']}")
    else:
        print("FLTCF not found")

if __name__ == "__main__":
    asyncio.run(check_fltcf())
