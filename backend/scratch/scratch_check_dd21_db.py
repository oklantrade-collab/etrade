import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== DD21_15M RULE DETAIL ===")
rule_res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Dd21_15m').execute()
if not rule_res.data:
    print("Rule not found.")
    sys.exit(0)

rule = rule_res.data[0]
for k, v in rule.items():
    print(f"  {k}: {v}")

cond_ids = rule.get('condition_ids', [])
print(f"\nConditions (IDs: {cond_ids}):")
if cond_ids:
    cond_res = sb.table('strategy_conditions').select('*').in_('id', cond_ids).execute()
    for c in cond_res.data:
        print("-" * 40)
        print(f"  ID: {c.get('id')}")
        print(f"  Name: {c.get('name')}")
        print(f"  Parameter: {c.get('parameter')}")
        print(f"  Operator: {c.get('operator')}")
        print(f"  Value: {c.get('value')}")
