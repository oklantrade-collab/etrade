import sys
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check_cond_usage():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('rule_code, cycle, condition_ids').execute()
    used_207 = []
    used_214 = []
    for r in res.data:
        c_ids = r.get('condition_ids', []) or []
        if 207 in c_ids:
            used_207.append(r['rule_code'] + " (" + r['cycle'] + ")")
        if 214 in c_ids:
            used_214.append(r['rule_code'] + " (" + r['cycle'] + ")")
            
    print(f"Cond 207 (EMA3 > EMA9) used in: {used_207}")
    print(f"Cond 214 (EMA3 < EMA9) used in: {used_214}")

if __name__ == "__main__":
    check_cond_usage()
