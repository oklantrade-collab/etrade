import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_evals():
    sb = get_supabase()
    print("--- ADAUSDT SYSTEM LOGS AROUND 05:30 UTC ---")
    logs = sb.table('system_logs').select('*').ilike('message', '%ADAUSDT%').gte('created_at', '2026-05-29T05:25:00').lte('created_at', '2026-05-29T05:55:00').order('created_at', desc=False).execute()
    for log in logs.data:
        print(f"[{log.get('created_at')}] {log.get('message')}")
        
    print("\n--- ADAUSDT EVALUATIONS AROUND 05:30 UTC ---")
    evals = sb.table('strategy_evaluations').select('*').eq('symbol', 'ADAUSDT').in_('rule_code', ['Aa21', 'Aa21_5m']).gte('created_at', '2026-05-29T05:25:00').lte('created_at', '2026-05-29T05:55:00').order('created_at', desc=False).execute()
    for e in evals.data:
        print(f"[{e.get('created_at')}] Rule: {e.get('rule_code')} Score: {e.get('total_score')} Passed: {e.get('passed')}")
        print(f"  Details: {e.get('condition_results')}")

if __name__ == "__main__":
    check_evals()
