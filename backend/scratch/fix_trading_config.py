import sys
import os
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def fix_config():
    sb = get_supabase()
    res = sb.table('trading_config').update({
        'mode': 'live',
        'paper_trading': False
    }).neq('id', 0).execute()
    print(f"Filas de trading_config actualizadas a live/paper=False: {len(res.data)}")
    
    # Confirm contents
    rows = sb.table('trading_config').select('id, mode, paper_trading').execute()
    for r in rows.data:
        print(f"ID {r['id']}: mode={r['mode']}, paper_trading={r['paper_trading']}")

if __name__ == "__main__":
    fix_config()
