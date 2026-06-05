import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def final_investigate():
    sb = get_supabase()
    print("--- ALL RULES ---")
    res = sb.table('trading_rules').select('*').execute()
    for row in res.data:
        name = row.get('rule_code') or row.get('name') or row.get('code')
        if '25' in str(name) or '21' in str(name) or 'Hot' in str(name):
            print(f"Found Rule: '{name}' | Enabled: {row.get('enabled')}")
            for c in row.get('conditions', []):
                print(f"  - {c}")

    print("\n--- ADAUSDT LOGS ---")
    logs = sb.table('system_logs').select('*').ilike('message', '%ADAUSDT%').gte('created_at', '2026-05-29T02:00:00').lte('created_at', '2026-05-29T03:00:00').execute()
    for log in logs.data:
        print(f"[{log.get('created_at')}] {log.get('level')} - {log.get('action')}: {log.get('message')}")

if __name__ == "__main__":
    final_investigate()
