import os
import sys
from datetime import datetime, timezone

# Ensure backend root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.core.supabase_client import get_supabase

def fix_sol_position():
    sb = get_supabase()
    pos_id = "a2dc76f1-4bad-4e4a-9fcb-3596e28e4a61"
    
    print(f"Updating position {pos_id} in Supabase...")
    
    # We will set closed_at to today (May 30, 2026) around 21:35:00 UTC (shortly before the screenshot at 21:48)
    closed_at_val = "2026-05-30T21:35:00+00:00"
    
    res = sb.table('positions').update({
        'closed_at': closed_at_val,
        'close_reason': 'MANUAL_DB_EDIT',
        'realized_pnl': 0.0,
        'realized_pnl_pct': 0.0
    }).eq('id', pos_id).execute()
    
    if res.data:
        print("Successfully repaired position SOLUSDT:")
        p = res.data[0]
        print(f"  ID: {p.get('id')}")
        print(f"  Closed At: {p.get('closed_at')}")
        print(f"  Close Reason: {p.get('close_reason')}")
        print(f"  Realized PnL: {p.get('realized_pnl')}")
    else:
        print("Failed to find or update position.")

if __name__ == "__main__":
    fix_sol_position()
