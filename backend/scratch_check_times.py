from app.core.supabase_client import get_supabase

def run():
    sb = get_supabase()
    res = sb.table('positions').select('id, symbol, opened_at, closed_at, erep_cycles_elapsed').eq('rule_code', 'Aa23').eq('status', 'closed').order('closed_at', desc=True).limit(3).execute()
    print("Times for closed positions:")
    for pos in res.data:
        print(f"ID={pos['id']}, symbol={pos['symbol']}")
        print(f"  opened_at={pos.get('opened_at')}")
        print(f"  closed_at={pos.get('closed_at')}")
        print(f"  erep_cycles_elapsed={pos.get('erep_cycles_elapsed')}")

if __name__ == '__main__':
    run()
