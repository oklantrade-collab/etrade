import os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.append(r'c:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase

sb = get_supabase()
rules = sb.table('trading_rules').select('id, rule_code').in_('rule_code', ['BbHot', 'Bb21', 'Bb25']).execute()

print("CONDITIONS FOR BbHot, Bb21, Bb25:")
for r in rules.data:
    print(f"\nRule: {r['rule_code']}")
    conds = sb.table('strategy_conditions').select('*').eq('rule_id', r['id']).execute()
    for c in conds.data:
        print(f"  {c['indicator_name']} {c['operator']} {c['value_type']} {c['threshold']} (eval_time={c.get('evaluation_time')})")
