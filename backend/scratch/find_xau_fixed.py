import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def find_xau_positions():
    sb = get_supabase()
    res = sb.table('positions').select('*').execute()
    print(f"Total positions in table: {len(res.data)}")
    
    xau_pos = [p for p in res.data if p['symbol'] and 'XAU' in p['symbol'].upper()]
    print(f"XAU related positions: {len(xau_pos)}")
    
    if xau_pos:
        for p in xau_pos:
            print(f"ID: {p['id']}, Symbol: {p['symbol']}, Status: {p['status']}, Realized: {p.get('realized_pnl')}, Unrealized: {p.get('unrealized_pnl')}")
    else:
        # Maybe it's in a different table?
        print("No XAU related positions in 'positions' table.")
        # Let's check 'orders' table too
        res_orders = sb.table('orders').select('*').ilike('symbol', '%XAU%').execute()
        print(f"XAU related orders: {len(res_orders.data)}")
        if res_orders.data:
            for o in res_orders.data[:5]:
                print(f"Order Symbol: {o['symbol']}")

if __name__ == "__main__":
    asyncio.run(find_xau_positions())
