import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def test_cols():
    sb = get_supabase()
    
    print("Checking Crypto 'positions' table for EREP columns...")
    try:
        res = sb.table('positions').select('id, erep_active, erep_phase, erep_p1_price, erep_p1_size').limit(1).execute()
        print("  OK! positions has EREP columns.")
        print(f"  Data sample: {res.data}")
    except Exception as e:
        print(f"  Error on positions: {e}")
        
    print("\nChecking Forex 'forex_positions' table for EREP columns...")
    try:
        res = sb.table('forex_positions').select('id, erep_active, erep_phase, erep_p1_price, erep_p1_size').limit(1).execute()
        print("  OK! forex_positions has EREP columns.")
        print(f"  Data sample: {res.data}")
    except Exception as e:
        print(f"  Error on forex_positions: {e}")

if __name__ == "__main__":
    test_cols()
