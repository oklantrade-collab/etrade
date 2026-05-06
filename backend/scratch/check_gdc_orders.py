import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_gdc_orders():
    sb = get_supabase()
    res = sb.table("stocks_orders").select("*").eq("ticker", "GDC").order("created_at", desc=True).limit(10).execute()
    for order in res.data:
        print(f"[{order['created_at']}] {order['direction']} {order['shares']} @ {order['market_price']} Rule: {order['rule_code']} Status: {order['status']}")

if __name__ == "__main__":
    asyncio.run(check_gdc_orders())
