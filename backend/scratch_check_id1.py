from app.core.supabase_client import get_supabase

def run():
    sb = get_supabase()
    res = sb.table('trading_config').select('*').eq('id', 1).execute()
    print("Row with id=1 in trading_config:", res.data)

if __name__ == '__main__':
    run()
