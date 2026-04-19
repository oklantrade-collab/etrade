import os, sys, json
from datetime import datetime, timezone
import asyncio

sys.path.insert(0, r'C:\Fuentes\eTrade\backend')
from app.core.supabase_client import get_supabase

def close_excess_positions():
    sb = get_supabase()
    
    # 1. Fetch risk config limit
    risk_res = sb.table('risk_config').select('max_positions_per_symbol').single().execute()
    max_pos = risk_res.data.get('max_positions_per_symbol', 3) if risk_res.data else 3
    print(f"Enforcing max positions per symbol: {max_pos}")
    
    # 2. Fetch all valid open positions for crypto
    pos_res = sb.table('positions').select('id, symbol, opened_at, close_reason').eq('status', 'open').execute()
    open_pos = pos_res.data or []
    
    # Filter only crypto positions (assume ending with USDT)
    crypto_pos = [p for p in open_pos if p.get('symbol', '').endswith('USDT')]
    
    # Group by symbol
    by_symbol = {}
    for p in crypto_pos:
        # normalize
        sym = p['symbol'].replace('/', '').upper()
        if sym not in by_symbol:
            by_symbol[sym] = []
        by_symbol[sym].append(p)
        
    print(f"Found {len(crypto_pos)} open crypto positions across {len(by_symbol)} symbols.")
    
    # 3. For each symbol, sort by opened_at descending (keep newest), and close the rest
    to_close = []
    now_iso = datetime.now(timezone.utc).isoformat()
    
    for sym, positions in by_symbol.items():
        # sort newest first
        positions.sort(key=lambda x: x.get('opened_at') or '', reverse=True)
        print(f" - {sym}: {len(positions)} open positions")
        
        if len(positions) > max_pos:
            excess = positions[max_pos:]
            print(f"   -> Closing {len(excess)} excess positions")
            for p in excess:
                to_close.append(p['id'])
                
    # 4. Close the excess
    for z in to_close:
        try:
            sb.table('positions').update({
                'status': 'closed', 
                'close_reason': 'limit_exceeded',
                'closed_at': now_iso
            }).eq('id', z).execute()
        except Exception as e:
            print(f"Error closing {z}: {e}")
            
    print(f"Closed {len(to_close)} excess positions. Cleanup complete.")

if __name__ == '__main__':
    close_excess_positions()
