import os
import sys
import json
from copy import deepcopy
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

sb = get_supabase()

def clone_rule(original_code, new_code, new_name):
    res = sb.table('trading_rules').select('*').eq('rule_code', original_code).execute()
    if not res.data:
        print(f"Original rule {original_code} not found in trading_rules.")
        return
    orig = res.data[0]
    
    exists = sb.table('trading_rules').select('id').eq('rule_code', new_code).execute()
    if not exists.data:
        max_id_res = sb.table('trading_rules').select('id').order('id', desc=True).limit(1).execute()
        max_id = max_id_res.data[0]['id'] if max_id_res.data else 0
        new_rule = deepcopy(orig)
        new_rule['id'] = max_id + 1
        new_rule['rule_code'] = new_code
        new_rule['name'] = new_name
        new_rule['description'] = (new_rule['description'] or "") + " (Crypto)"
        sb.table('trading_rules').insert(new_rule).execute()
        print(f"Created {new_code} in trading_rules.")

    res2 = sb.table('strategy_rules_v2').select('*').eq('rule_code', original_code).execute()
    if res2.data:
        orig2 = res2.data[0]
        exists2 = sb.table('strategy_rules_v2').select('id').eq('rule_code', new_code).execute()
        if not exists2.data:
            max_id2_res = sb.table('strategy_rules_v2').select('id').order('id', desc=True).limit(1).execute()
            max_id2 = max_id2_res.data[0]['id'] if max_id2_res.data else 0
            new_rule2 = deepcopy(orig2)
            new_rule2['id'] = max_id2 + 1
            new_rule2['rule_code'] = new_code
            sb.table('strategy_rules_v2').insert(new_rule2).execute()
            print(f"Created {new_code} in strategy_rules_v2.")

clone_rule('Aa30', 'Aa30C', 'LONG 5m Cripto')
clone_rule('Bb30', 'Bb30C', 'SHORT 5m Cripto')
