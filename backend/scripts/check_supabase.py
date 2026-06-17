import asyncio
import os
import sys
from datetime import datetime
import pytz

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    
    # 3. Top Apex Scores
    print("\n--- APEX SCORES ---")
    apex_res = sb.table("apex_scores").select("ticker, apex_score_4h, apex_score_1d, confidence").order("apex_score_4h", desc=True).limit(5).execute()
    for row in apex_res.data:
        print(f"{row['ticker']}: 4H={row['apex_score_4h']}, 1D={row['apex_score_1d']}, Conf={row['confidence']}")

    # 4. Market Hours check
    ny_tz = pytz.timezone('America/New_York')
    ny_time = datetime.now(ny_tz)
    print(f"\nNY Time: {ny_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Is Weekend? {ny_time.weekday() >= 5}")

if __name__ == "__main__":
    asyncio.run(check())
