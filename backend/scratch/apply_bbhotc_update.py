import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def update_bbhotc():
    sb = get_supabase()
    
    # 1. Update strategy_conditions ID 229 description & name for clarity in UI
    sb.table('strategy_conditions').update({
        'name': 'Cruce SHORT & Proximidad 98% a EMA20 (EMA3<EMA9<EMA20)',
        'description': 'Gatilla SHORT directo de momentum al estar alineadas EMA3 < EMA9 < EMA20 y alcanzar el 98% de la EMA20'
    }).eq('id', 229).execute()

    # 2. Update strategy_rules_v2 for BbHotC
    # Condition IDs: 214 (EMA3<EMA9), 215 (EMA9<EMA20), 229 (Cruce & Proximidad 98%), 73 (EMA20 Desc 1h)
    new_cond_ids = [214, 215, 229, 73]
    new_weights = {'214': 0.35, '215': 0.35, '229': 0.20, '73': 0.10}
    
    r2_res = sb.table('strategy_rules_v2').update({
        'min_score': 0.70,
        'condition_ids': new_cond_ids,
        'condition_weights': new_weights,
    }).eq('rule_code', 'BbHotC').execute()
    
    print("Actualizada regla BbHotC en strategy_rules_v2: min_score=0.70")
    
    # 3. Verify updated row in strategy_rules_v2
    updated = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'BbHotC').execute()
    if updated.data:
        r = updated.data[0]
        print(f"Verificacion DB: Code={r['rule_code']} | Min Score={r['min_score']} | Cond IDs={r['condition_ids']} | Weights={r['condition_weights']}")

if __name__ == "__main__":
    update_bbhotc()
