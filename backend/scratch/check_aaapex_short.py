import os, sys, json
from dotenv import load_dotenv
load_dotenv()
sys.path.append(r'c:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase

sb = get_supabase()
rules = sb.table('trading_rules').select('id, rule_code').execute()

print("ALL RULE CODES:")
for r in rules.data:
    print(r['rule_code'])
