from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('positions').select('symbol').ilike('symbol', '%ADA%').execute()
for p in res.data:
    sym = p['symbol']
    print(f"{sym}: {sym.encode().hex()}")
