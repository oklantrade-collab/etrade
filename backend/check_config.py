import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_db():
    sb = get_supabase()
    res = sb.table('strategy_variables').select('*').like('name', '%RSI%').execute()
    print("Variables RSI:")
    for row in res.data:
        print(row)

if __name__ == "__main__":
    check_db()
