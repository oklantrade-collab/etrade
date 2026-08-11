import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def apply_forex_guard():
    sb = get_supabase()
    res = sb.table('trading_config').update({
        'min_profit_exit_pips_forex': 3.0,
        'min_profit_exit_pips_gold': 15.0,
        'be_trigger_pips_forex': 5.0,
        'be_buffer_pips_forex': 1.0
    }).neq('id', 0).execute()
    print(f"Filas actualizadas en trading_config para Forex (Min PnL +3.0 pips / Gold +15.0 pips / BE +5.0 pips): {len(res.data)}")
    
    rows = sb.table('trading_config').select('id, min_profit_exit_pips_forex, min_profit_exit_pips_gold, be_trigger_pips_forex').execute()
    for r in rows.data:
        print(f"ID {r['id']}: min_pips_forex={r.get('min_profit_exit_pips_forex')}, min_pips_gold={r.get('min_profit_exit_pips_gold')}, be_trigger={r.get('be_trigger_pips_forex')}")

if __name__ == "__main__":
    apply_forex_guard()
