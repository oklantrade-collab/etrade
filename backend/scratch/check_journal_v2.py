import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_journal_v2():
    sb = get_supabase()
    res = sb.table("trades_journal").select("*").order("exit_date", desc=True).limit(20).execute()
    for entry in res.data:
        print(f"[{entry['exit_date']}] {entry['ticker']} PnL: {entry['pnl_usd']}$ Reason: {entry.get('exit_reason', 'N/A')}")

if __name__ == "__main__":
    asyncio.run(check_journal_v2())
