import asyncio
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_logs():
    sb = get_supabase()
    res = sb.table('system_logs').select('*').eq('module', 'STOCKS_ENGINE').order('created_at', desc=True).limit(20).execute()
    print("--- STOCKS ENGINE LOGS ---")
    for r in res.data:
        print(f"[{r['created_at']}] {r['message']} | {r.get('context')}")
    
    res2 = sb.table('system_logs').select('*').eq('module', 'stocks_scheduler').order('created_at', desc=True).limit(10).execute()
    print("\n--- SCHEDULER LOGS ---")
    for r in res2.data:
        print(f"[{r['created_at']}] {r['message']}")

if __name__ == "__main__":
    asyncio.run(check_logs())
