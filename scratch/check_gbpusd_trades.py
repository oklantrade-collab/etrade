import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

def check_positions():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('symbol', 'GBPUSD').order('closed_at', desc=True).limit(5).execute()
    print("=== GBPUSD Recent Closed Positions ===")
    if res.data:
        for pos in res.data:
            print(f"ID: {pos['id']}")
            print(f"Side: {pos['side']}")
            print(f"Rule Code: {pos['rule_code']}")
            print(f"Opened At: {pos['opened_at']}")
            print(f"Closed At: {pos['closed_at']}")
            print(f"Entry Price: {pos['entry_price']}")
            print(f"Close Price: {pos['current_price']}")
            print(f"Lots: {pos['lots']}")
            print(f"PnL USD: {pos['pnl_usd']}")
            print(f"PnL Pips: {pos['pnl_pips']}")
            print(f"Close Reason: {pos['close_reason']}")
            print("-" * 40)
    else:
        print("No GBPUSD positions found")

    # Also check the snapshot for GBPUSD
    res_snap = sb.table('market_snapshot').select('*').eq('symbol', 'GBPUSD').execute()
    print("=== GBPUSD Snapshot ===")
    if res_snap.data:
        for k, v in res_snap.data[0].items():
            if k in ['symbol', 'price', 'basis', 'atr', 'updated_at', 'upper_1', 'lower_1']:
                print(f"{k}: {v}")
    else:
        print("No snapshot found for GBPUSD")

if __name__ == "__main__":
    check_positions()
