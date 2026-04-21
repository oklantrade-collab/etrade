import os
from datetime import datetime, timezone
import sys
sys.path.append('backend')

from dotenv import load_dotenv
load_dotenv('backend/.env')

from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error

async def cleanup_losing_trades():
    sb = get_supabase()
    now_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    # Fetch open positions opened today
    res = sb.table('stocks_positions')\
        .select('*')\
        .eq('status', 'open')\
        .gte('first_buy_at', now_date)\
        .execute()
    
    positions = res.data or []
    to_close = [p for p in positions if (p.get('unrealized_pnl') or 0) < 0]
    
    if not to_close:
        print("No losing positions opened today found.")
        return

    print(f"Found {len(to_close)} losing positions to close.")
    
    curr_time = datetime.now(timezone.utc).isoformat()
    
    for pos in to_close:
        ticker = pos['ticker']
        pnl = pos['unrealized_pnl']
        print(f"Closing {ticker} with P&L: {pnl}")
        
        # 1. Archive in journal
        journal_entry = {
            "ticker": ticker,
            "shares": int(float(pos.get("shares", 0))),
            "entry_price": float(pos.get("avg_price", 0)),
            "exit_price": float(pos.get("current_price", 0)),
            "entry_date": pos.get("first_buy_at"),
            "exit_date": curr_time,
            "pnl_usd": float(pos.get("unrealized_pnl", 0)),
            "pnl_pct": float(pos.get("unrealized_pnl_pct", 0)),
            "result": "loss",
            "exit_reason": "manual_cleanup_loss_today",
        }
        sb.table("trades_journal").insert(journal_entry).execute()

        # 2. Mark as closed
        sb.table("stocks_positions").update({
            "status": "closed",
            "updated_at": curr_time
        }).eq("id", pos['id']).execute()
        
    print("Cleanup completed.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(cleanup_losing_trades())
