from app.core.supabase_client import get_supabase

def check_logs():
    sb = get_supabase()
    res = sb.table('system_logs').select('*').like('message', '%603b7188%').execute()
    print("Logs for Trade 603b7188:")
    for row in res.data:
        print(f"{row['created_at']} | {row['message']}")

    res_all = sb.table('system_logs').select('*').order('created_at', desc=True).limit(50).execute()
    print("\nRecent general system logs:")
    for row in res_all.data:
        if any(keyword in str(row.values()).lower() for keyword in ('aa23', 'erep', 'timeout', 'close_all')):
            print(f"{row['created_at']} | {row.get('level')} | {row.get('message')}")

if __name__ == '__main__':
    check_logs()
