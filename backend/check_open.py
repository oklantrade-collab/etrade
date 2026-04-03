from app.core.supabase_client import get_supabase

sb = get_supabase()
res = sb.table('positions').select('*').eq('status', 'open').execute()
print(f"OPEN POSITIONS ({len(res.data)}):")
for r in res.data:
    print(r)
