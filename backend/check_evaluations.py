import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_evals():
    sb = get_supabase()
    
    print("--- Recent Evaluations for SHORT (direction=short) ---")
    try:
        # What are the columns? Let's check first.
        # We got an error before for 'action', which means 'action' does not exist.
        # Let's inspect the columns of strategy_evaluations by fetching 1 row.
        test_res = sb.table('strategy_evaluations').select('*').limit(1).execute()
        if test_res.data:
            print("Columns in strategy_evaluations:", list(test_res.data[0].keys()))
            
            # Let's fetch recent short evaluations.
            res = sb.table('strategy_evaluations')\
                .select('*')\
                .like('rule_code', 'Bb%')\
                .order('created_at', desc=True)\
                .limit(20)\
                .execute()
                
            for row in res.data:
                print(f"Time: {row['created_at']} | Symbol: {row['symbol']} | Rule: {row['rule_code']} | Triggered: {row.get('triggered')} | Score: {row.get('score')} | Context: {row.get('context')}")
        else:
            print("No evaluations in strategy_evaluations table.")
    except Exception as e:
        print(f"Error checking evaluations: {e}")

if __name__ == "__main__":
    check_evals()
