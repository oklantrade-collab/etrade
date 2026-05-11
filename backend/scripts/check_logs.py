from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('system_logs').select('message, created_at').limit(100).order('created_at', desc=True).execute()
for l in res.data:
    msg = l['message']
    if 'LIMIT' in msg or 'BLOCK' in msg or 'ADA' in msg:
        print(f"{l['created_at']}: {msg}")
