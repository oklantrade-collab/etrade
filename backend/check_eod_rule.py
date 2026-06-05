import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_eod_rule():
    sb = get_supabase()
    res = sb.table('trading_rules').select('*').eq('rule_code', 'AaEOD').execute()
    if res.data:
        rule = res.data[0]
        print(f"Code: {rule['rule_code']}")
        print(f"Condition: {rule['condition_expression']}")
        print(f"Status: {rule['is_active']}")
    else:
        print("Rule AaEOD not found in DB.")

if __name__ == "__main__":
    check_eod_rule()
