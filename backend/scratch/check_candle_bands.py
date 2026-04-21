from app.core.supabase_client import get_supabase

sb = get_supabase()

# Check XAUUSD candle data
res = sb.table('market_candles').select(
    'basis, upper_6, lower_6, upper_1, lower_1'
).eq('symbol', 'XAUUSD').eq('timeframe', '15m').order(
    'open_time', desc=True
).limit(10).execute()

print("=== XAUUSD candle bands (last 10) ===")
for r in res.data:
    print(f"basis={r['basis']}, u1={r['upper_1']}, u6={r['upper_6']}, l1={r['lower_1']}, l6={r['lower_6']}")

# Also check snapshot
snap = sb.table('market_snapshot').select(
    'basis, upper_6, lower_6, upper_1, lower_1'
).eq('symbol', 'XAUUSD').execute()
print("\n=== XAUUSD snapshot ===")
for r in snap.data:
    print(f"basis={r['basis']}, u1={r['upper_1']}, u6={r['upper_6']}, l1={r['lower_1']}, l6={r['lower_6']}")

# Check the exchange field for Forex candles
exch = sb.table('market_candles').select('exchange').eq('symbol', 'XAUUSD').eq('timeframe', '15m').limit(1).execute()
print(f"\n=== Exchange for XAUUSD: {exch.data} ===")
