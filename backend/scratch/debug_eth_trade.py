from app.core.supabase_client import get_supabase
import json

def debug_trade():
    sb = get_supabase()
    
    # 1. Query paper_trades
    res = sb.table('paper_trades').select('*').eq('id', 'a0ece069-8bf3-467a-a3c6-5c32c7cde54c').execute()
    print("=== Paper Trade ===")
    if res.data:
        print(json.dumps(res.data[0], indent=2))
    else:
        print("Paper trade not found.")
        
    # 2. Query positions (closed) matching the symbol and time around 2026-06-08T11:05
    res_pos = sb.table('positions').select('*').eq('symbol', 'ETHUSDT').eq('status', 'closed').order('closed_at', desc=True).limit(5).execute()
    print("\n=== Closed Positions ===")
    for p in res_pos.data:
        print(f"ID={p['id']}, rule={p.get('rule_code')}, entry={p.get('entry_price')}, sl={p.get('sl_price') or p.get('stop_loss')}, closed_at={p.get('closed_at')}, close_reason={p.get('close_reason')}, realized_pnl={p.get('realized_pnl')}")
        # Print EREP-related fields
        print(f"  erep_phase={p.get('erep_phase')}, erep_active={p.get('erep_active')}, slv_price={p.get('slv_price')}, recovery_mode={p.get('recovery_mode')}")

    # 3. Query system_logs around that time
    res_logs = sb.table('system_logs').select('*').order('created_at', desc=True).limit(200).execute()
    print("\n=== Recent System Logs ===")
    for log in res_logs.data:
        msg = log.get('message') or ''
        # Look for the trade ID, or the symbol ETHUSDT, or EREP, or SLV
        if any(x in msg for x in ('a0ece069', 'ETHUSDT', 'erep', 'SLVM', 'SLV', 'close')):
            print(f"{log['created_at']} | {log['level']} | {msg}")

if __name__ == '__main__':
    debug_trade()
