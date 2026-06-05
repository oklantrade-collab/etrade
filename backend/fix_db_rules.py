import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def fix_rules():
    sb = get_supabase()
    
    cids = [205, 207, 208, 211, 213, 225, 227]
    weights = {
        '205': 0.1,
        '207': 0.3,
        '208': 0.1,
        '211': 0.2,
        '213': 0.2,
        '225': 0.1,
        '227': 0.1
    }
    
    sb.table('strategy_rules_v2').update({
        'condition_ids': cids,
        'condition_weights': weights,
        'min_score': 1.0,
        'condition_logic': 'AND'
    }).eq('rule_code', 'Aa21').execute()
    print("Fixed Aa21 IDs")

if __name__ == "__main__":
    fix_rules()
