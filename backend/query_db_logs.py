import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_logs():
    sb = get_supabase()
    res = sb.table('system_logs')\
        .select('*')\
        .ilike('message', '%GBPUSD%')\
        .gte('created_at', '2026-05-29T00:00:00+00:00')\
        .order('created_at', desc=True)\
        .execute()
        
    print(f"Found {len(res.data)} logs for GBPUSD today:")
    for log in res.data[:50]:
        print(f"[{log.get('created_at')}] [{log.get('module')}] [{log.get('level')}] {log.get('message')}")
        if log.get('context'):
            print("  Context:", log.get('context'))

if __name__ == "__main__":
    check_logs()
