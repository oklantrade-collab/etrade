import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_logs():
    sb = get_supabase()
    print("\n--- ADAUSDT ANY LOGS AROUND THOSE TIMES ---")
    logs = sb.table('system_logs').select('*').ilike('message', '%ADAUSDT%').gte('created_at', '2026-07-19T03:30:00').lte('created_at', '2026-07-19T08:30:00').ilike('message', '%EREP%').order('created_at', desc=False).execute()
    for log in logs.data:
        print(f"[{log.get('created_at')}] {log.get('level')} - {log.get('action')}: {log.get('message')}")

if __name__ == '__main__':
    check_logs()
