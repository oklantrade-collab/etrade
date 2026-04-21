from app.core.supabase_client import get_supabase
import json

def check_config():
    sb = get_supabase()
    res = sb.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
    print(json.dumps(res.data, indent=2))

if __name__ == "__main__":
    check_config()
