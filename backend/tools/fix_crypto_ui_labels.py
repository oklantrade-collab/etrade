import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from app.core.supabase_client import get_supabase

def fix_db_configs():
    sb = get_supabase()
    
    # 1. Update condition ID 73 ('EMA20 Descendiendo 1h')
    print("Updating strategy_conditions for ID 73...")
    res = sb.table('strategy_conditions').update({
        "timeframe": "1h",
        "description": "EMA20 descendiendo en 1h (vela actual < vela previa)"
    }).eq('id', 73).execute()
    print("Updated condition 73:", res.data)
    
    # 2. Update rule 'BbHot' in strategy_rules_v2 (point to 229 instead of 223)
    print("Updating strategy_rules_v2 for 'BbHot'...")
    res = sb.table('strategy_rules_v2').update({
        "condition_ids": [229],
        "condition_weights": {"229": 0.8}
    }).eq('rule_code', 'BbHot').execute()
    print("Updated BbHot:", res.data)
    
    # 3. Update rule 'BbHotC' in strategy_rules_v2 (point to 229 and 73)
    print("Updating strategy_rules_v2 for 'BbHotC'...")
    res = sb.table('strategy_rules_v2').update({
        "condition_ids": [229, 73],
        "condition_weights": {"229": 0.8, "73": 0.2}
    }).eq('rule_code', 'BbHotC').execute()
    print("Updated BbHotC:", res.data)

if __name__ == "__main__":
    fix_db_configs()
