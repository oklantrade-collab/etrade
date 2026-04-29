import asyncio
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_hot_candle_rule():
    sb = get_supabase()
    res = sb.table("stocks_rules").select("*").eq("rule_code", "HOT_CANDLE_BUY").execute()
    if res.data:
        r = res.data[0]
        print(f"--- RULE: {r['rule_code']} ---")
        print(f"IA Min: {r.get('ia_min')}")
        print(f"Tech Min: {r.get('tech_score_min')}")
        print(f"Pine Required: {r.get('pine_required')}")
        print(f"SIPV Required: {r.get('sipv_required')}")
        print(f"SIPV Signal: {r.get('sipv_signal')}")
        print(f"RVOL Min: {r.get('rvol_min')}")
    else:
        print("Rule not found")

if __name__ == "__main__":
    asyncio.run(check_hot_candle_rule())
