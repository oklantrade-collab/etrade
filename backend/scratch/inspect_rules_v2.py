import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def inspect():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('*').in_('rule_code', ['AaHotC', 'Aa13', 'Aa22']).execute()
    
    # Get all strategy conditions map
    c_res = sb.table('strategy_conditions').select('id, name').execute()
    c_map = {c['id']: c['name'] for c in c_res.data}
    
    for row in res.data:
        print("="*60)
        print(f"Rule Code: {row.get('rule_code')} (ID: {row.get('id')})")
        print(f"Min Score: {row.get('min_score')}")
        print("Conditions & Weights:")
        c_ids = row.get('condition_ids', [])
        c_weights = row.get('condition_weights', {})
        for cid in c_ids:
            name = c_map.get(cid, f"Unknown condition {cid}")
            w = c_weights.get(str(cid))
            print(f"  - ID {cid}: {name} (Weight: {w})")

if __name__ == "__main__":
    inspect()
