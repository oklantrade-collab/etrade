import asyncio
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_rules():
    sb = get_supabase()
    res = sb.table("stocks_rules").select("*").eq("enabled", True).execute()
    print("--- ACTIVE RULES ---")
    for r in res.data:
        print(f"Code: {r['rule_code']} | Dir: {r['direction']} | Group: {r['group_name']} | IA: {r.get('ia_min')} | SM: {r.get('sm_min')} | Pine: {r.get('pine_signal')}")
    
    print("\n--- RECENT SNAPSHOTS (Sample) ---")
    snap_res = sb.table("technical_scores").select("*").order("timestamp", desc=True).limit(5).execute()
    for s in snap_res.data:
        print(f"Ticker: {s['ticker']} | Score: {s['technical_score']} | IA: {s.get('pro_score')} | Pool: {s.get('pool_type')} | Pine: {s.get('pinescript_signal')}")

if __name__ == "__main__":
    asyncio.run(check_rules())
