import os
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime, timezone, timedelta
from collections import defaultdict

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not found in .env")
    exit(1)

sb = create_client(url, key)

cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
res = sb.table('pilot_diagnostics') \
    .select('symbol, cycle_type, timestamp') \
    .gte('timestamp', cutoff) \
    .order('timestamp', desc=True) \
    .execute()

by_symbol = defaultdict(set)
for r in res.data:
    by_symbol[r['symbol']].add(r['cycle_type'])

print("Estado Frankfurt post-deploy Sprint 5:")
for sym, cycles in sorted(by_symbol.items()):
    # Convert sets to sorted lists for consistent output
    print(f"  {sym:8} -> {sorted(list(cycles))}")

expected = {'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT'}
found = set(by_symbol.keys())
missing = expected - found
print(f"\nFaltantes: {missing if missing else 'Ninguno - OK'}")
