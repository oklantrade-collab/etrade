import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def inspect_bb():
    sb = get_supabase()
    c_res = sb.table('strategy_conditions').select('id, name').execute()
    cond_map = {c['id']: c for c in (c_res.data or [])}

    r_res = sb.table('strategy_rules_v2').select('*').in_('rule_code', ['BbHotC', 'Bb13', 'Bb21']).execute()
    
    print("="*70)
    print("INSPECCION DETALLADA DE BbHotC, Bb13 y Bb21")
    print("="*70)
    for r in r_res.data:
        code = r.get('rule_code')
        score = r.get('min_score')
        print(f"\n[REGLA {code}] | Min Score: {score}")
        cond_ids = r.get('condition_ids', [])
        weights = r.get('condition_weights', {})
        for cid in cond_ids:
            info = cond_map.get(cid, {})
            name = info.get('name', f'ID {cid}')
            w = weights.get(str(cid), '?')
            print(f"   - [{cid}] {name} -> Peso: {w}")

if __name__ == "__main__":
    inspect_bb()
