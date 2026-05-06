import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_forex_losses():
    sb = get_supabase()
    # Looking for recent Forex (EURUSD, GBPUSD) losses in trades_journal
    res = sb.table("trades_journal").select("*").in_("ticker", ["EURUSD", "GBPUSD"]).order("exit_date", desc=True).limit(20).execute()
    for entry in res.data:
        print(f"[{entry['exit_date']}] {entry['ticker']} Exit: {entry['exit_price']} Reason: {entry['exit_reason']} PnL: {entry['pnl_usd']}$ ({entry['pnl_pct']}%)")

if __name__ == "__main__":
    asyncio.run(check_forex_losses())
