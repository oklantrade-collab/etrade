import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== SEARCHING ALL SIGNALS ===")
res = sb.table('trading_signals').select('*').limit(100).execute()

symbols = set()
rules = set()

for s in res.data:
    symbols.add(s.get('symbol'))
    rules.add(s.get('rule_code') or s.get('rule'))
    if 'EUR' in str(s.get('symbol')).upper():
        print(f"Match: {s}")

print(f"\nSymbols: {symbols}")
print(f"Rules: {rules}")
