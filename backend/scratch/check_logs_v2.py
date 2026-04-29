import asyncio
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_logs():
    sb = get_supabase()
    modules = ['STOCKS_ENGINE', 'stocks_order_exec', 'stocks_scheduler']
    print("--- SYSTEM LOGS ---")
    res = sb.table('system_logs').select('*').in_('module', modules).order('created_at', desc=True).limit(50).execute()
    for r in res.data:
        print(f"[{r['created_at']}] [{r['module']}] {r['message']}")

if __name__ == "__main__":
    asyncio.run(check_logs())
