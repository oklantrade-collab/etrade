from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('stocks_config').select('key, value').execute()
for r in (res.data or []):
    print(f"{r['key']} | {r['value']}")
