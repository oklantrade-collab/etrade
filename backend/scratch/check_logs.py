from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('system_logs').select('*').limit(20).execute()
for r in (res.data or []):
    print(f"{r['created_at']} | {r['module']} | {r['message']}")
