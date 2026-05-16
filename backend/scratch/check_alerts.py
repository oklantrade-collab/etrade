from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('alert_events').select('*').ilike('message', '%KILL SWITCH%').order('sent_at', desc=True).limit(10).execute()
for r in (res.data or []):
    print(f"{r['sent_at']} | {r['message']}")
