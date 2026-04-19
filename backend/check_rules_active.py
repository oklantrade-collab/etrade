
import os
import sys
from datetime import date
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set UTF-8 encoding for stdout
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.core.supabase_client import get_supabase

sb = get_supabase()

def check_today():
    today = date.today().isoformat()
    print(f"--- ACTIVE RULES REPORT ---")
    
    res_rules = sb.table('stocks_rules').select('*').eq('enabled', True).execute()
    if res_rules.data:
        for r in res_rules.data:
            print(f"\nRule: {r['rule_code']} ({r['direction']} {r['order_type']})")
            print(f"- IA Min: {r.get('ia_min')}")
            print(f"- Tech Min: {r.get('tech_score_min')}")
            print(f"- Fund Min: {r.get('fundamental_score_min')}")
            print(f"- RVOL Min: {r.get('rvol_min')}")
            print(f"- movements: {r.get('movements_allowed')}")
            print(f"- pine: {r.get('pine_signal')} (req: {r.get('pine_required')})")
    else:
        print("No active rules found in stocks_rules!")

if __name__ == "__main__":
    check_today()
