import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def inspect():
    sb = get_supabase()
    try:
        res = sb.table('trading_config').select('*').limit(5).execute()
        print("Data:", res.data)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    inspect()
