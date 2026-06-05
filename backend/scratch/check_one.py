import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from app.core.supabase_client import get_supabase

def check_one():
    sb = get_supabase()
    res = sb.table('positions').select('*').eq('id', '8d9ee233-0cfd-463a-a3fa-491b24a87f55').execute()
    if res.data:
        p = res.data[0]
        for k, v in p.items():
            print(f"{k}: {v}")
            
if __name__ == "__main__":
    check_one()
