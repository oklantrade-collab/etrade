import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_pos():
    sb = get_supabase()
    res = sb.table('positions').select('*').eq('id', 'd4cdb257-1e31-478b-bebc-036540a3f73a').execute()
    if res.data:
        for k, v in res.data[0].items():
            print(f"{k}: {v}")

    print("\n--- POS LOGS ---")
    logs = sb.table('system_logs').select('*').ilike('message', '%d4cdb257-1e31-478b-bebc-036540a3f73a%').order('created_at', desc=False).execute()
    for log in logs.data:
        print(f"[{log.get('created_at')}] {log.get('level')} - {log.get('action')}: {log.get('message')}")

if __name__ == '__main__':
    check_pos()
