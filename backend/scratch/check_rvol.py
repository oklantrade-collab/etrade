import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_rvol():
    sb = get_supabase()
    res = sb.table("technical_scores").select("*").eq("ticker", "BDRX").execute()
    if res.data:
        sigs = res.data[0].get('signals_json')
        if isinstance(sigs, str):
            import json
            sigs = json.loads(sigs)
        print(f"Ticker: BDRX, RVOL: {sigs.get('rvol')}")
        print(f"EMA3: {sigs.get('ema_3')}, EMA9: {sigs.get('ema_9')}, EMA20: {sigs.get('ema_20')}")
        print(f"BB Expanding: {sigs.get('bb_expanding')}")
    else:
        print("BDRX not found")

if __name__ == "__main__":
    asyncio.run(check_rvol())
