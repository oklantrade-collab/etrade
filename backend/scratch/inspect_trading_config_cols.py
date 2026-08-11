import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def check_cols():
    sb = get_supabase()
    res = sb.table('trading_config').select('*').eq('id', 1).execute()
    if res.data:
        print("Column names in trading_config:")
        for k in sorted(res.data[0].keys()):
            print("  -", k)

if __name__ == "__main__":
    check_cols()
