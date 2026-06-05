from app.core.supabase_client import get_supabase

def run():
    sb = get_supabase()
    res = sb.table('positions').select('*').eq('status', 'open').execute()
    print("Open positions:")
    for pos in res.data:
        print(f"ID={pos['id']}, symbol={pos['symbol']}, side={pos['side']}, rule_code={pos['rule_code']}, erep_active={pos.get('erep_active')}, erep_phase={pos.get('erep_phase')}, erep_cycles={pos.get('erep_cycles_elapsed')}, created_at={pos.get('created_at')}")

if __name__ == '__main__':
    run()
