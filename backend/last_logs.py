from app.core.supabase_client import get_supabase
import sys

def last_logs():
    sb = get_supabase()
    res = sb.table('system_logs')\
            .select('message, created_at, level')\
            .order('created_at', desc=True)\
            .limit(50)\
            .execute()
            
    for r in res.data[::-1]: # Chronological
        print(f"{r['created_at']}: [{r['level']}] {r['message']}")

if __name__ == "__main__":
    last_logs()
