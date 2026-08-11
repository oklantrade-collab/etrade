import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def update_bb_lower():
    sb = get_supabase()
    
    # 1. Clarify condition ID 9914 description in strategy_conditions
    sb.table('strategy_conditions').update({
        'name': 'BB Lower Descending 15m (2-3 velas)',
        'description': 'La Banda Inferior de Bollinger muestra movimiento en descenso en las últimas 2 o 3 velas de 15m'
    }).eq('id', 9914).execute()
    print("Actualizada condición 9914 en strategy_conditions")

    # 2. Update strategy_rules_v2 for BbHotC
    # Condition IDs: 214 (EMA3<EMA9), 215 (EMA9<EMA20), 229 (Proximidad 98%), 9914 (BB Lower Descending), 73 (EMA20 Desc 1h)
    new_cond_ids = [214, 215, 229, 9914, 73]
    new_weights = {
        '214': 0.30,
        '215': 0.30,
        '229': 0.20,
        '9914': 0.15,
        '73': 0.05
    }
    
    r2_res = sb.table('strategy_rules_v2').update({
        'min_score': 0.70,
        'condition_ids': new_cond_ids,
        'condition_weights': new_weights,
    }).eq('rule_code', 'BbHotC').execute()
    
    print("Actualizada regla BbHotC en strategy_rules_v2 con BB Lower Descending")
    
    # 3. Verify updated row
    updated = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'BbHotC').execute()
    if updated.data:
        r = updated.data[0]
        print(f"Verificacion DB: Code={r['rule_code']} | Min Score={r['min_score']} | Cond IDs={r['condition_ids']} | Weights={r['condition_weights']}")

if __name__ == "__main__":
    update_bb_lower()
