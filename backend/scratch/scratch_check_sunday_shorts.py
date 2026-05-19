import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== CHECKING SUNDAY SHORT TRADES ===")
res = sb.table('forex_positions') \
    .select('*') \
    .gte('opened_at', '2026-05-17T23:00:00+00:00') \
    .execute()

for p in res.data:
    print("-" * 50)
    print(f"ID: {p.get('id')}")
    print(f"Symbol: {p.get('symbol')}")
    print(f"Side: {p.get('side')}")
    print(f"Rule Code: {p.get('rule_code')}")
    print(f"Status: {p.get('status')}")
    print(f"PnL USD: {p.get('pnl_usd')}")
    print(f"Close Reason: {p.get('close_reason') or p.get('exit_reason')}")
    print(f"Opened At: {p.get('opened_at')}")
    print(f"Closed At: {p.get('closed_at')}")
