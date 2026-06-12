import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.core.supabase_client import get_supabase

async def check_position():
    sb = get_supabase()
    # Search for closed XAUUSD positions
    res = sb.table("forex_positions").select("*").eq("symbol", "XAUUSD").eq("status", "closed").order("closed_at", desc=True).limit(5).execute()
    
    if res.data:
        print(f"Found {len(res.data)} closed XAUUSD positions")
        for p in res.data:
            print("---")
            print(f"ID: {p.get('id')} / {p.get('ctrader_order_id')}")
            print(f"Side: {p.get('side')}, Size: {p.get('lots')}")
            print(f"Entry Date: {p.get('opened_at')}, Price: {p.get('entry_price')}")
            print(f"Close Date: {p.get('closed_at')}, Price: {p.get('exit_price')}")
            print(f"Strategy Entry: {p.get('rule_code')}")
            print(f"Strategy Exit: {p.get('close_reason')}")
            print(f"PNL: {p.get('pnl_usd')}")
    else:
        # Maybe it's in a different table?
        res2 = sb.table("positions").select("*").eq("symbol", "XAUUSD").eq("status", "closed").order("closed_at", desc=True).limit(5).execute()
        if res2.data:
            print(f"Found in 'positions' table")
            for p in res2.data:
                print(p)
        else:
            print("No closed XAUUSD positions found.")

if __name__ == "__main__":
    asyncio.run(check_position())
