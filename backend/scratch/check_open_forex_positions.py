from app.core.supabase_client import get_supabase

def run():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').order('opened_at', desc=True).limit(20).execute()
    print("Recent Forex positions with opened_at:")
    for pos in res.data:
        print(f"ID={pos['id']}, symbol={pos['symbol']}, side={pos['side']}, opened_at={pos.get('opened_at')}, closed_at={pos.get('closed_at')}, status={pos.get('status')}, sl={pos.get('sl_price')}, tp={pos.get('tp_price')}")

if __name__ == '__main__':
    run()
