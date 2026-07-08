import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_trade():
    sb = get_supabase()
    print("=== DIAGNOSING ALL GBPUSD FOREX TRADES FOR TODAY ===")
    
    # Query paper_trades table for GBPUSD closed today
    res = sb.table('paper_trades')\
        .select('*')\
        .eq('symbol', 'GBPUSD')\
        .execute()
        
    if not res.data:
        print("No trades found in paper_trades for GBPUSD")
        return
        
    for idx, t in enumerate(res.data, 1):
        print(f"\n--- Trade #{idx} ---")
        print(f"ID: {t.get('id')}")
        print(f"Side: {t.get('side')}")
        print(f"Entry Price: {t.get('entry_price')}")
        print(f"Exit Price: {t.get('exit_price')}")
        print(f"PnL USD: ${t.get('total_pnl_usd') or t.get('pnl_usd')}")
        print(f"PnL %: {t.get('total_pnl_pct') or t.get('pnl_pct')}%")
        print(f"Opened At: {t.get('opened_at')}")
        print(f"Closed At: {t.get('closed_at')}")
        print(f"Close Reason: {t.get('close_reason') or t.get('exit_reason')}")
        print(f"Rule Code: {t.get('rule_code')}")

if __name__ == "__main__":
    check_trade()
