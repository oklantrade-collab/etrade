import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== SEARCHING FOR RULES IN strategy_rules_v2 ===")
res = sb.table('strategy_rules_v2').select('*').execute()

for r in res.data:
    code = r.get('rule_code', '')
    if any(x in code.lower() for x in ['aa31', 'bb31']):
        print(f"Code: {code} | Name: {r.get('name')} | Direction: {r.get('direction')} | Enabled: {r.get('is_active')}")
        print(f"  Conditions: {r.get('conditions')}")
        print(f"  Weights: {r.get('weights')}")
        print("-" * 50)
