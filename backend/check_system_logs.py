from app.core.supabase_client import get_supabase

def check_logs():
    sb = get_supabase()
    res = sb.table('system_logs').select('*').order('created_at', desc=True).limit(50).execute()
    for l in res.data:
        print(f"[{l.get('created_at')}] {l.get('module')} | {l.get('message')}")

if __name__ == "__main__":
    check_logs()
