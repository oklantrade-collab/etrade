import os
import sys
import json
from datetime import datetime, timezone

sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase

def cleanup_zombie_positions():
    sb = get_supabase()
    
    # 1. Fetch active_symbols from trading_config
    res_cfg = sb.table('trading_config').select('active_symbols').eq('id', 1).maybe_single().execute()
    active_raw = res_cfg.data.get('active_symbols', []) if res_cfg.data else []
    
    if isinstance(active_raw, str):
        try:
            active_raw = json.loads(active_raw)
        except Exception:
            active_raw = [s.strip() for s in active_raw.split(',') if s.strip()]
            
    # Normalize permitted symbols
    active_norm = [s.replace('/', '').upper() for s in active_raw]
    print(f"Allowed symbols: {active_norm}")
    
    # 2. Fetch ALL open Crypto positions (rule_entry like 'crypto%' or from candle_signal, or simply check ALL open positions against cryptos)
    # Actually, let's just fetch all open positions, and check if symbol matches a forbidden crypto format (BTCUSDT, etc.)
    # We will close any position ending with USDT or USD if it's NOT in active_norm
    res_pos = sb.table('positions').select('id, symbol, rule_code').eq('status', 'open').execute()
    open_positions = res_pos.data or []
    
    zombies = []
    for p in open_positions:
        sym = p.get('symbol', '').replace('/', '').upper()
        # Ensure it's a crypto symbol, not a forex or stock. Assuming Forex are 6 chars no USD/USDT ending unless exceptions?
        # Typically Crypto ends in USDT or USDC.
        if "USDT" in sym or "USD" in sym:
            # It's a crypto or forex. If it's crypto and ends in USDT
            if sym.endswith("USDT") and sym not in active_norm:
                zombies.append(p['id'])
                
    print(f"Total open positions checked: {len(open_positions)}")
    print(f"Zombies to close: {len(zombies)}")
    
    # 3. Close the zombies
    now_iso = datetime.now(timezone.utc).isoformat()
    for z in zombies:
        sb.table('positions').update({
            'status': 'closed', 
            'close_reason': 'unauthorized_symbol',
            'closed_at': now_iso
        }).eq('id', z).execute()
        
    print("Cleanup complete.")

if __name__ == '__main__':
    cleanup_zombie_positions()
