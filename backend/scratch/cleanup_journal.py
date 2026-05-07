from app.core.supabase_client import get_supabase

sb = get_supabase()
# Check journal
res = sb.table("trades_journal").select("*").eq("ticker", "USDJPY").gt("pnl_usd", 100000).execute()

if res.data:
    for row in res.data:
        print(f"Journal ID: {row['id']}, PNL: {row['pnl_usd']}")
        sb.table("trades_journal").delete().eq("id", row['id']).execute()
        print("Deleted from trades_journal.")
else:
    print("No bad records in trades_journal.")
