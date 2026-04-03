from app.core.supabase_client import get_supabase
import sys

def diag_1():
    sb = get_supabase()
    time_limit = '2026-03-21T13:00:00Z'
    
    # Simple query first to avoid complex ILIKE OR strings via API if not familiar
    res = sb.table('system_logs')\
            .select('message, created_at, level')\
            .gt('created_at', time_limit)\
            .order('created_at', desc=False)\
            .limit(100)\
            .execute()
            
    filtered = []
    keywords = ['Error', 'error', 'Exception', '15m', 'cycle']
    for row in res.data:
        msg = row['message']
        if any(k in msg for k in keywords):
            filtered.append(row)
            
    print(f"DIAGNÓSTICO 1 (15m cycle / Errors since 13:00 UTC):")
    for r in filtered[:20]:
        print(f"{r['created_at']}: [{r['level']}] {r['message']}")

if __name__ == "__main__":
    diag_1()
