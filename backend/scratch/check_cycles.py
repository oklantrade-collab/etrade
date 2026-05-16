from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('cron_cycles').select('*').order('started_at', desc=True).limit(50).execute()
for r in (res.data or []):
    print(f"{r['started_at']} | {r['status']} | {r['symbols_analyzed']}")
