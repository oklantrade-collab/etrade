from app.core.supabase_client import get_supabase

def check_reasons():
    sb = get_supabase()
    res = sb.table('paper_trades').select('*').eq('rule_code', 'Aa23').order('created_at', desc=True).limit(3).execute()
    print("Columns for recent Aa23 trades:")
    for row in res.data:
        print(f"ID={row['id']}")
        print(f"  exit_reason={row.get('exit_reason')}")
        print(f"  exit_trigger_price={row.get('exit_trigger_price')}")
        print(f"  stop_loss={row.get('stop_loss')}")
        print(f"  take_profit={row.get('take_profit')}")
        print(f"  pnl_realized={row.get('pnl_realized')}")
        print(f"  status={row.get('status')}")

if __name__ == '__main__':
    check_reasons()
