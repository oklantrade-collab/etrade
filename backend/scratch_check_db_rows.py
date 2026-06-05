import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_db_rows():
    sb = get_supabase()
    
    print("--- TRADING CONFIG ---")
    try:
        res = sb.table('trading_config').select('*').execute()
        print(f"Total rows in trading_config: {len(res.data)}")
        if res.data:
            print("First 3 rows:")
            for i, row in enumerate(res.data[:3]):
                print(f"Row {i}: id={row.get('id')}, key={row.get('key')}, value={row.get('value')}")
    except Exception as e:
        print("Error in trading_config:", e)

    print("\n--- RISK CONFIG ---")
    try:
        res = sb.table('risk_config').select('*').execute()
        print(f"Total rows in risk_config: {len(res.data)}")
        if res.data:
            print("First 3 rows:")
            for i, row in enumerate(res.data[:3]):
                print(f"Row {i}: id={row.get('id')}, max_open_trades={row.get('max_open_trades')}")
    except Exception as e:
        print("Error in risk_config:", e)

if __name__ == "__main__":
    check_db_rows()
