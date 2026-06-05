import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_v2_rules():
    sb = get_supabase()
    print("--- STRATEGY RULES V2 ---")
    res = sb.table('strategy_rules_v2').select('*').in_('rule_code', ['Aa21', 'Aa21_5m', 'AaHot', 'Aa25']).execute()
    
    cond_ids = []
    for r in res.data:
        cond_ids.extend(r.get('condition_ids', []))
        
    conds = {}
    if cond_ids:
        c_res = sb.table('strategy_conditions').select('*').in_('id', cond_ids).execute()
        for c in c_res.data:
            conds[c['id']] = c

    for r in res.data:
        print(f"\nRule: {r['rule_code']} (Enabled: {r.get('enabled')})")
        c_ids = r.get('condition_ids', [])
        c_wts = r.get('condition_weights', {})
        if isinstance(c_wts, list):
            c_wts = {str(i): w for i, w in enumerate(c_wts)}
        for idx, cid in enumerate(c_ids):
            w = c_wts.get(str(idx), 0)
            c = conds.get(cid, {})
            print(f"  - {c.get('name', 'Unknown')}: {c.get('indicator')} {c.get('operator')} {c.get('value')} (Weight: {w})")

if __name__ == "__main__":
    check_v2_rules()
