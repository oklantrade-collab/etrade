import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def get_logs():
    sb = get_supabase()
    logs = sb.table('system_logs').select('*').ilike('message', '%ADAUSDT%').gte('created_at', '2026-07-19T02:50:00').lte('created_at', '2026-07-19T05:00:00').order('created_at', desc=False).execute()
    for log in logs.data:
        print(f"[{log.get('created_at')}] {log.get('level')} - {log.get('action')}: {log.get('message')}")

if __name__ == '__main__':
    get_logs()
