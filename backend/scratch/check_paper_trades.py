import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_paper_trades_forex():
    sb = get_supabase()
    res = sb.table("paper_trades").select("*").order("closed_at", desc=True).limit(50).execute()
    for p in res.data:
        sym = p['symbol']
        if any(x in sym for x in ["EUR", "GBP", "USD", "JPY", "XAU"]):
             print(f"[{p['closed_at']}] {p['symbol']} {p['side']} Entry: {p['entry_price']} Exit: {p['exit_price']} Reason: {p['close_reason']} PnL: {p.get('total_pnl_usd')}$ ({p.get('total_pnl_pct')}%)")

if __name__ == "__main__":
    asyncio.run(check_paper_trades_forex())
