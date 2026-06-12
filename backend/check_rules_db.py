import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_rules():
    sb = get_supabase()
    
    print("--- Enabled rules in strategy_rules_v2 ---")
    res = sb.table('strategy_rules_v2').select('rule_code, name, direction, enabled, cycle').execute()
    for row in res.data:
        print(f"Code: {row['rule_code']} | Name: {row['name']} | Direction: {row['direction']} | Enabled: {row['enabled']} | Cycle: {row['cycle']}")

if __name__ == "__main__":
    check_rules()
