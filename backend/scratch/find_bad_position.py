from app.core.supabase_client import get_supabase

sb = get_supabase()
res = sb.table("forex_positions").select("*").eq("symbol", "USDJPY").gt("pnl_usd", 100000).execute()

if res.data:
    for pos in res.data:
        print(f"ID: {pos['id']}, Symbol: {pos['symbol']}, PNL: {pos['pnl_usd']}, Created: {pos['opened_at']}")
else:
    print("No position found matching the criteria.")
