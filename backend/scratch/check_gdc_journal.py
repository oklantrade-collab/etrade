import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_gdc_journal():
    sb = get_supabase()
    res = sb.table("trades_journal").select("*").eq("ticker", "GDC").order("exit_date", desc=True).limit(5).execute()
    for entry in res.data:
        print(f"[{entry['exit_date']}] Exit: {entry['exit_price']} Reason: {entry['exit_reason']} PnL: {entry['pnl_pct']}%")

if __name__ == "__main__":
    asyncio.run(check_gdc_journal())
