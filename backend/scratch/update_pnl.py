import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.supabase_client import get_supabase

async def update_db():
    sb = get_supabase()
    
    pos_id = "6b0fcd30-f67e-4672-9baf-3d4cfb5978f8"
    new_pnl = 170.30
    old_pnl = 1703.05
    
    # Update forex_positions
    res1 = sb.table("forex_positions").update({"pnl_usd": new_pnl}).eq("id", pos_id).execute()
    print("forex_positions update:", res1.data)
    
    # Check paper_trades
    res2 = sb.table("paper_trades").select("*").eq("symbol", "XAUUSD").eq("total_pnl_usd", old_pnl).execute()
    if res2.data:
        trade_id = res2.data[0]["id"]
        res3 = sb.table("paper_trades").update({"total_pnl_usd": new_pnl}).eq("id", trade_id).execute()
        print("paper_trades update:", res3.data)
    else:
        print("No matching paper_trades found.")

if __name__ == "__main__":
    asyncio.run(update_db())
