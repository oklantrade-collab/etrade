import asyncio
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_opps():
    sb = get_supabase()
    res = sb.table('trade_opportunities').select('*').order('created_at', desc=True).limit(10).execute()
    print("--- RECENT OPPORTUNITIES ---")
    for r in res.data:
        print(f"[{r['created_at']}] {r['ticker']} | Status: {r['status']} | MetaScore: {r['meta_score']}")

if __name__ == "__main__":
    asyncio.run(check_opps())
