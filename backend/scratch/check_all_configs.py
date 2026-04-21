from app.core.supabase_client import get_supabase
import json

def check_risk():
    sb = get_supabase()
    res = sb.table('risk_config').select('*').limit(1).execute()
    print("RISK_CONFIG:")
    print(json.dumps(res.data, indent=2))
    
    res2 = sb.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
    print("\nTRADING_CONFIG:")
    print(json.dumps(res2.data, indent=2))

if __name__ == "__main__":
    check_risk()
