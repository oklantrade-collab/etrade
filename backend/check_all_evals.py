import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_evals():
    sb = get_supabase()
    print("--- ALL EVALUATIONS AROUND 05:30 UTC ---")
    evals = sb.table('strategy_evaluations').select('symbol, rule_code, score, triggered, created_at').gte('created_at', '2026-05-29T05:25:00').lte('created_at', '2026-05-29T05:55:00').execute()
    for e in evals.data:
        print(f"[{e.get('created_at')}] [{e.get('symbol')}] Rule: {e.get('rule_code')} Score: {e.get('score')} Triggered: {e.get('triggered')}")

if __name__ == "__main__":
    check_evals()
