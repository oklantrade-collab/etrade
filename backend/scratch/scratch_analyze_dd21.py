import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== FOREX_POSITIONS DD21 DETAILS ===")
res = sb.table('forex_positions') \
    .select('*') \
    .eq('symbol', 'EURUSD') \
    .execute()

dd21_positions = []
for p in res.data:
    rule = str(p.get('rule_code') or p.get('rule_entry') or '').lower()
    if 'dd21' in rule:
        dd21_positions.append(p)

print(f"Encontradas {len(dd21_positions)} posiciones de DD21 en forex_positions:")
for p in sorted(dd21_positions, key=lambda x: x.get('opened_at', '')):
    print("-" * 50)
    print(f"ID: {p.get('id')}")
    print(f"Opened At: {p.get('opened_at')}")
    print(f"Closed At: {p.get('closed_at')}")
    print(f"Side: {p.get('side')}")
    print(f"Lots: {p.get('lots')}")
    print(f"Entry Price: {p.get('entry_price')}")
    print(f"Close Price: {p.get('close_price') or p.get('current_price')}")
    print(f"PnL USD: {p.get('pnl_usd')}")
    print(f"PnL Pips: {p.get('pnl_pips')}")
    print(f"Close Reason: {p.get('close_reason') or p.get('exit_reason')}")
