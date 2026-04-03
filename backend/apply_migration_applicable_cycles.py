import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def apply_migration():
    sb = get_supabase()
    
    queries = [
        "ALTER TABLE strategy_rules_v2 ADD COLUMN IF NOT EXISTS applicable_cycles TEXT[] DEFAULT '{15m}';",
        "UPDATE strategy_rules_v2 SET applicable_cycles = ARRAY[cycle] WHERE applicable_cycles IS NULL;",
        "UPDATE strategy_rules_v2 SET applicable_cycles = '{5m,15m}' WHERE rule_code = 'Aa23';",
        "UPDATE strategy_rules_v2 SET applicable_cycles = '{5m,15m}' WHERE rule_code = 'Bb23';",
        "UPDATE strategy_rules_v2 SET applicable_cycles = '{15m}' WHERE rule_code IN ('Aa11','Aa12','Aa21','Aa22','Aa24','Bb11','Bb12','Bb21','Bb22');",
        "UPDATE strategy_rules_v2 SET applicable_cycles = '{15m,4h}' WHERE rule_code IN ('Dd21_15m','Dd21_4h','Dd11_15m','Dd11_4h');"
    ]
    
    for q in queries:
        try:
            print(f"Executing: {q}")
            sb.rpc('exec_sql', {'sql_query': q}).execute()
            print("  OK")
        except Exception as e:
            print(f"  Error: {e}")
            # If RPC fails, we might need manual execution.
            # But let's see if it works first.

    # Verify
    print("\nVerifying migration:")
    try:
        res = sb.table('strategy_rules_v2').select('rule_code, cycle, applicable_cycles').order('rule_code').execute()
        if res.data:
            print(f"{'rule_code':<10} | {'cycle':<6} | {'applicable_cycles'}")
            print("-" * 40)
            for row in res.data:
                print(f"{row['rule_code']:<10} | {row['cycle']:<6} | {row['applicable_cycles']}")
        else:
            print("No data found.")
    except Exception as e:
        print(f"Verification failed: {e}")

if __name__ == "__main__":
    apply_migration()
