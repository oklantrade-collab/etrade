from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('trading_signals').select('*').order('created_at', desc=True).limit(20).execute()
for r in (res.data or []):
    print(f"{r['created_at']} | {r['symbol']} | {r['status']} | {r['rejection_reason']}")
