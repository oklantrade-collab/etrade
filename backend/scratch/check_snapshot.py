from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('market_snapshot').select('symbol, updated_at').in_('symbol', ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT']).execute()
for r in (res.data or []):
    print(f"{r['symbol']} | {r['updated_at']}")
