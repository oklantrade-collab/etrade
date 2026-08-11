import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def audit():
    sb = get_supabase()
    
    # 1. Fetch conditions map
    c_res = sb.table('strategy_conditions').select('id, name').execute()
    cond_map = {c['id']: c['name'] for c in (c_res.data or [])}

    # 2. Fetch strategy_rules_v2
    r2_res = sb.table('strategy_rules_v2').select('*').execute()
    rules_v2 = r2_res.data or []

    print("="*80)
    print(f"AUDITORIA COMPLETA DE ESTRATEGIAS (Total V2: {len(rules_v2)})")
    print("="*80)

    for r in sorted(rules_v2, key=lambda x: str(x.get('rule_code', ''))):
        code = r.get('rule_code')
        score = r.get('min_score')
        cond_ids = r.get('condition_ids', [])
        weights = r.get('condition_weights', {})
        print(f"\n[REGLA {code}] | Min Score: {score}")
        for cid in cond_ids:
            name = cond_map.get(cid, f"Condition {cid}")
            w = weights.get(str(cid), '?')
            print(f"   - {name} (ID {cid}): Peso {w}")

if __name__ == "__main__":
    audit()
