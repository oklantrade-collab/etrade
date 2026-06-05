import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_config():
    sb = get_supabase()
    res = sb.table('trading_config').select('regime_params').eq('id', 1).execute()
    print("=== trading_config regime_params ===")
    if res.data:
        print(res.data[0].get('regime_params'))
    else:
        print("No config found")

if __name__ == "__main__":
    check_config()
