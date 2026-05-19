import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== SEARCHING ALL HISTORIC POSITIONS ===")
res = sb.table('positions').select('symbol, rule_code, rule_entry, realized_pnl, status, close_reason, opened_at').execute()

by_symbol = {}
by_rule = {}

for p in res.data:
    symbol = p.get('symbol')
    rule = p.get('rule_code') or p.get('rule_entry')
    pnl = p.get('realized_pnl')
    
    by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
    by_rule[rule] = by_rule.get(rule, 0) + 1
    
    if 'EUR' in str(symbol) or 'DD21' in str(rule).upper():
        print(f"Match: Symbol={symbol} | Rule={rule} | PnL={pnl} | Reason={p.get('close_reason')} | Status={p.get('status')} | Opened={p.get('opened_at')}")

print("\nAll Symbols count:")
for k, v in by_symbol.items():
    print(f"  {k}: {v}")

print("\nAll Rules count:")
for k, v in by_rule.items():
    print(f"  {k}: {v}")
