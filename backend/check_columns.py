import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check():
    sb = get_supabase()
    
    tables = ['positions', 'forex_positions', 'stocks_positions']
    
    for table in tables:
        try:
            print(f"\nChecking table '{table}':")
            res = sb.table(table).select("*").limit(1).execute()
            if res.data:
                row = res.data[0]
                keys = list(row.keys())
                erep_keys = [k for k in keys if k.startswith('erep_')]
                print(f"  Total columns: {len(keys)}")
                print(f"  EREP columns found: {erep_keys}")
            else:
                print("  Table exists but has no rows. Trying to insert a dummy or inspect schema cache by selecting specific columns...")
                # Let's try selecting specific EREP columns to see if they fail
                test_cols = ['erep_active', 'erep_phase', 'erep_p1_price']
                try:
                    res_cols = sb.table(table).select(",".join(test_cols)).limit(1).execute()
                    print(f"  Columns {test_cols} exist!")
                except Exception as ex_col:
                    print(f"  Selecting {test_cols} failed: {ex_col}")
        except Exception as e:
            print(f"  Failed to query table '{table}': {e}")

if __name__ == "__main__":
    check()
