import asyncio
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase

async def debug_trades():
    sb = get_supabase()
    tickers = ['DSGN', 'IHRT']
    
    print(f"DEBUGGING TRADES: {tickers}")
    
    # 1. Check in journal
    print("\n--- JOURNAL ---")
    res = sb.table("trades_journal").select("*").in_("ticker", tickers).order("exit_date", desc=True).limit(2).execute()
    for row in res.data:
        print(f"Ticker: {row['ticker']} | Exit Price: {row['exit_price']} | PnL%: {row['pnl_pct']} | Reason: {row['exit_reason']}")

    # 2. Check in positions table (even if closed)
    print("\n--- POSITIONS TABLE ---")
    res = sb.table("stocks_positions").select("*").in_("ticker", tickers).order("updated_at", desc=True).limit(2).execute()
    for row in res.data:
        print(f"Ticker: {row['ticker']} | Entry: {row['avg_price']} | SL: {row['stop_loss']} | SLV: {row['slv_price']} | Recovery Mode: {row['recovery_mode']} | SL Type: {row['sl_type']}")

if __name__ == "__main__":
    asyncio.run(debug_trades())
