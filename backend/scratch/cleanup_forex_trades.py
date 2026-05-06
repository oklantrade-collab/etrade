import asyncio
import os
import sys
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def cleanup_fictitious_forex():
    sb = get_supabase()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    try:
        # 1. Delete from forex_positions
        res_fx = sb.table("forex_positions").delete().gte("closed_at", today).execute()
        print(f"Deleted {len(res_fx.data) if res_fx.data else 0} closed Forex positions from today.")
        
        # 2. Delete from paper_trades (Forex ones)
        # Note: paper_trades might not have a 'market' column, but we can filter by symbol
        forex_symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'EUR/USD', 'GBP/USD', 'USD/JPY', 'XAU/USD']
        res_paper = sb.table("paper_trades").delete().in_("symbol", forex_symbols).gte("closed_at", today).execute()
        print(f"Deleted {len(res_paper.data) if res_paper.data else 0} paper trades from today.")
        
    except Exception as e:
        print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    asyncio.run(cleanup_fictitious_forex())
