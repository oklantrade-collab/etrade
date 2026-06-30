import os
import json
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

sb = get_supabase()

print("--- EVALUATIONS ---")
evals = sb.table('strategy_evaluations').select('*').eq('symbol', 'XAUUSD').eq('rule_code', 'Aa30').gte('created_at', '2026-06-24T23:55:00').lte('created_at', '2026-06-25T00:05:00').execute()
for e in evals.data:
    print(json.dumps(e, indent=2))

print("--- POSITIONS ---")
pos = sb.table('forex_positions').select('*').eq('symbol', 'XAUUSD').gte('opened_at', '2026-06-24T23:55:00').lte('opened_at', '2026-06-25T00:05:00').execute()
for p in pos.data:
    print(json.dumps(p, indent=2))
