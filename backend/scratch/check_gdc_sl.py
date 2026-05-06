import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_gdc_sl():
    sb = get_supabase()
    res = sb.table("stocks_positions").select("*").eq("ticker", "GDC").eq("status", "closed").execute()
    if res.data:
        pos = res.data[-1]
        print(f"Ticker: {pos['ticker']}")
        print(f"Entry: {pos['avg_price']}")
        print(f"Stop Loss: {pos.get('stop_loss')}")
        print(f"TP Trailing SL: {pos.get('tp_trailing_sl')}")
        print(f"TP Trailing High: {pos.get('tp_trailing_high')}")
        print(f"Current Price (at close): {pos.get('current_price')}")
        print(f"Close Reason: {pos.get('sl_close_reason')}")
    else:
        print("GDC closed positions not found")

if __name__ == "__main__":
    asyncio.run(check_gdc_sl())
