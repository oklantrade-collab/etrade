import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_rules():
    sb = get_supabase()
    res = sb.table('trading_rules').select('*').limit(1).execute()
    if res.data:
        print("Columns in trading_rules:", list(res.data[0].keys()))

    res2 = sb.table('trading_rules').select('*').execute()
    for row in res2.data:
        name = row.get('rule_code') or row.get('name') or row.get('code')
        if name in ['Aa21', 'Aa21_5m', 'AaHot']:
            print(f"Rule: {name} | Active: {row.get('is_active') or row.get('active')}")
            for c in row.get('conditions', []):
                print(f"  - {c}")

if __name__ == "__main__":
    check_rules()
