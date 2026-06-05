import asyncio
from app.core.supabase_client import get_supabase

async def query():
    sb = get_supabase()
    
    # Check forex rules
    print("--- RULES ---")
    res_rules = sb.table("forex_rules").select("*").eq("rule_code", "AA31A").execute()
    if res_rules.data:
        for r in res_rules.data:
            print(r)
    else:
        # try without case sensitivity or wildcard
        res_rules2 = sb.table("forex_rules").select("*").execute()
        for r in res_rules2.data:
            if "AA" in r.get("rule_code", "").upper() or "31" in r.get("rule_code", ""):
                print(r)
                
    # Check forex positions
    print("\n--- POSITIONS ---")
    res_pos = sb.table("forex_positions").select("*").eq("symbol", "USDJPY").order("created_at", desc=True).limit(5).execute()
    for p in res_pos.data:
        print(f"ID: {p['id']}, Open: {p['open_time']}, Close: {p['close_time']}, PnL: {p.get('unrealized_pnl') or p.get('realized_pnl')}, Rule: {p.get('entry_rule_code')}, Entry: {p['entry_price']}, SL: {p.get('stop_loss')}")

if __name__ == "__main__":
    asyncio.run(query())
