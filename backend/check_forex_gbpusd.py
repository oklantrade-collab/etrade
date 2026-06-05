import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_gbpusd():
    sb = get_supabase()
    res = sb.table('forex_positions').select('*').eq('symbol', 'GBPUSD').order('opened_at', desc=True).limit(5).execute()
    print("=== GBPUSD Positions ===")
    for p in res.data:
        print("ID:", p.get('id'))
        print("Symbol:", p.get('symbol'))
        print("Side:", p.get('side'))
        print("Lots:", p.get('lots'))
        print("Entry Price:", p.get('entry_price'))
        print("SL Price:", p.get('sl_price'))
        print("TP Price:", p.get('tp_price'))
        print("Status:", p.get('status'))
        print("Opened At:", p.get('opened_at'))
        print("Closed At:", p.get('closed_at'))
        print("Close Reason:", p.get('close_reason'))
        print("PnL USD:", p.get('pnl_usd'))
        print("PnL Pips:", p.get('pips_pnl') or p.get('pips') or p.get('pnl_pips'))
        print("EREP Active:", p.get('erep_active'))
        print("EREP Phase:", p.get('erep_phase'))
        print("EREP P1 Price:", p.get('erep_p1_price'))
        print("EREP Q1:", p.get('erep_q1'))
        print("EREP Close Reason:", p.get('erep_close_reason'))
        print("---------------------------------")

if __name__ == "__main__":
    check_gbpusd()
