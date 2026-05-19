import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== REAL CONDITIONS AND WEIGHTS ===")
res = sb.table('strategy_rules_v2').select('rule_code,condition_ids,condition_weights').execute()

for r in res.data:
    code = r.get('rule_code', '')
    if any(x in code.lower() for x in ['aa31', 'bb31']):
        print(f"Code: {code}")
        print(f"  Condition IDs: {r.get('condition_ids')}")
        print(f"  Weights: {r.get('condition_weights')}")
        print("-" * 50)
