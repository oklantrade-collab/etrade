import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== STRATEGY CONDITIONS DETAILS ===")
cond_ids = [56, 46, 52, 54, 26, 57, 47, 55, 27, 50]
res = sb.table('strategy_conditions').select('*, variable:strategy_variables(*)').in_('id', cond_ids).execute()

for c in res.data:
    var = c.get('variable') or {}
    print(f"ID: {c.get('id')} | Name: {c.get('name')}")
    print(f"  Field: {var.get('source_field')} | Operator: {c.get('operator')} | Value: {c.get('value_literal') or c.get('value_variable')}")
    print("-" * 50)
