import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== EURUSD TRADING SIGNALS ===")
res = sb.table('trading_signals') \
    .select('*') \
    .eq('symbol', 'EURUSD') \
    .order('created_at', desc=True) \
    .limit(30) \
    .execute()

for s in res.data:
    print("-" * 50)
    print(f"ID: {s.get('id')}")
    print(f"Created At: {s.get('created_at')}")
    print(f"Direction: {s.get('direction') or s.get('side')}")
    print(f"Rule Code: {s.get('rule_code')}")
    print(f"Score: {s.get('score')}")
    print(f"Triggered: {s.get('triggered')}")
    print(f"Executed: {s.get('executed') or s.get('status')}")
    print(f"Reason: {s.get('reason') or s.get('detail')}")
