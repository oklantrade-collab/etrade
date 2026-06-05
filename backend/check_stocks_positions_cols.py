import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_cols():
    sb = get_supabase()
    res = sb.table('stocks_positions').select('*').limit(1).execute()
    if res.data:
        print("Columns in stocks_positions:")
        print(list(res.data[0].keys()))
    else:
        print("No rows in stocks_positions to inspect columns.")

if __name__ == "__main__":
    check_cols()
