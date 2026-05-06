import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_forex_losses_v2():
    sb = get_supabase()
    res = sb.table("trades_journal").select("*").order("exit_date", desc=True).limit(50).execute()
    for entry in res.data:
        ticker = entry.get('ticker', '')
        if 'EUR' in ticker or 'GBP' in ticker or 'USD' in ticker:
             print(f"[{entry['exit_date']}] {ticker} Exit: {entry['exit_price']} Reason: {entry['exit_reason']} PnL: {entry['pnl_usd']}$")

if __name__ == "__main__":
    asyncio.run(check_forex_losses_v2())
