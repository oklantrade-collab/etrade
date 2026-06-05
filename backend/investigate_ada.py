import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def investigate_ada():
    sb = get_supabase()
    print("--- RULES CONDITIONS ---")
    res = sb.table('trading_rules').select('*').execute()
    for row in res.data:
        name = row.get('rule_code') or row.get('name') or row.get('code')
        if name in ['Aa25', 'Aa21', 'Aa21_5m', 'AaHot']:
            print(f"Rule: {name} (Enabled/Active: {row.get('enabled') or row.get('is_active') or row.get('active')})")
            for c in row.get('conditions', []):
                print(f"  - {c}")

    print("\n--- ADAUSDT SYSTEM LOGS AROUND 02:07 UTC ---")
    logs = sb.table('system_logs').select('*').ilike('message', '%ADAUSDT%').gte('timestamp', '2026-05-29T02:05:00').lte('timestamp', '2026-05-29T02:55:00').order('timestamp', desc=False).execute()
    for log in logs.data:
        print(f"[{log.get('timestamp')}] {log.get('level')} - {log.get('action')}: {log.get('message')}")

if __name__ == "__main__":
    investigate_ada()
