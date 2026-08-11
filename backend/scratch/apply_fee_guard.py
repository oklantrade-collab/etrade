import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def apply_guard():
    sb = get_supabase()
    res = sb.table('trading_config').update({
        'min_profit_exit_pct': 0.25,
        'min_profit_exit_usd': 0.50
    }).neq('id', 0).execute()
    print(f"Filas actualizadas en trading_config con Fee-Net Profit Guard (0.25% / $0.50 USD): {len(res.data)}")
    
    rows = sb.table('trading_config').select('id, min_profit_exit_pct, min_profit_exit_usd').execute()
    for r in rows.data:
        print(f"ID {r['id']}: min_profit_exit_pct={r.get('min_profit_exit_pct')}, min_profit_exit_usd={r.get('min_profit_exit_usd')}")

if __name__ == "__main__":
    apply_guard()
