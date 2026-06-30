from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('system_logs').select('*').order('created_at', desc=True).limit(50).execute()
with open('recent_logs_dump.txt', 'w', encoding='utf-8') as f:
    for l in res.data:
        f.write(f"{l['created_at']} | {l['module']} | {l['message']}\n")
