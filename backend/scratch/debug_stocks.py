from app.core.supabase_client import get_supabase
import json

def main():
    sb = get_supabase()
    res = sb.table('stocks_config').select('key, value').execute()
    for r in res.data:
        print(f"{r['key']}: {r['value']}")
    
    # Also check the last order for GRWG
    res_order = sb.table('stocks_orders').select('*').eq('ticker', 'GRWG').order('created_at', desc=True).limit(1).execute()
    if res_order.data:
        print("\nLast GRWG Order:")
        print(json.dumps(res_order.data[0], indent=2))

if __name__ == '__main__':
    main()
