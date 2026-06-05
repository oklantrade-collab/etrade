import asyncio
from app.core.supabase_client import get_supabase

async def query():
    sb = get_supabase()
    
    # Check forex positions
    print("--- POSITIONS ---")
    res_pos = sb.table("forex_positions").select("*").eq("symbol", "USDJPY").order("opened_at", desc=True).limit(10).execute()
    for p in res_pos.data:
        print(f"ID: {p['id']}")
        print(f"Open: {p.get('opened_at')}, Close: {p.get('closed_at')}")
        print(f"Entry: {p['entry_price']}, Exit: {p.get('close_price')}")
        print(f"SL: {p.get('sl_price')}, Reason: {p.get('close_reason')}")
        print(f"Lots: {p.get('lots')}")
        print(f"PnL pips: {p.get('pnl_pips')}, PnL USD: {p.get('pnl_usd')}")
        print("---")

if __name__ == "__main__":
    asyncio.run(query())
