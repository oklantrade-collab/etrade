import sys
import json
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check_aahotc():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'AaHotC').execute()
    for rule in res.data:
        print(f"Rule Code: {rule['rule_code']}")
        print(f"Min Score: {rule['min_score']}")
        print(f"Logic: {rule['condition_logic']}")
        
        c_ids = rule.get('condition_ids', [])
        c_weights = rule.get('condition_weights', {})
        print("Conditions mapping:")
        
        cond_res = sb.table('strategy_conditions').select('id, name, source_code').in_('id', c_ids).execute()
        for cond in cond_res.data:
            w = c_weights.get(str(cond['id']))
            print(f"  - [{cond['id']}] {cond['name']} (Weight: {w}) -> Source: {cond.get('source_code')}")

if __name__ == "__main__":
    check_aahotc()
