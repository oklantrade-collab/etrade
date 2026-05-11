from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('positions').select('symbol, status').ilike('symbol', '%ADA%').execute()
for p in res.data:
    sym = p['symbol']
    stat = p['status']
    print(f"Sym: |{sym}| ({sym.encode().hex()}), Status: |{stat}| ({stat.encode().hex()})")
