from app.core.supabase_client import get_supabase

def run():
    sb = get_supabase()
    res = sb.table('positions').select('*').eq('rule_code', 'Aa23').eq('status', 'closed').order('closed_at', desc=True).limit(3).execute()
    print("Closed positions for Aa23:")
    for pos in res.data:
        print(f"ID={pos['id']}, symbol={pos['symbol']}")
        print(f"  erep_active={pos.get('erep_active')}")
        print(f"  erep_phase={pos.get('erep_phase')}")
        print(f"  erep_cycles_elapsed={pos.get('erep_cycles_elapsed')}")
        print(f"  close_reason={pos.get('close_reason')}")
        print(f"  stop_loss={pos.get('stop_loss')}")
        print(f"  entry_price={pos.get('entry_price')}")
        print(f"  current_price={pos.get('current_price')}")

if __name__ == '__main__':
    run()
