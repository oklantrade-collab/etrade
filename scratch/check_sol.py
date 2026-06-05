import os
import sys

# Ensure backend root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.core.supabase_client import get_supabase

def check_sol_positions():
    sb = get_supabase()
    
    # Query positions for SOLUSDT
    print("Searching in 'positions' table for SOLUSDT...")
    res = sb.table('positions').select('*').eq('symbol', 'SOLUSDT').order('id').execute()
    data = res.data or []
    
    print(f"Found {len(data)} positions:")
    for pos in data:
        print(f"ID: {pos.get('id')}")
        print(f"  Status: {pos.get('status')}")
        print(f"  Side: {pos.get('side')}")
        print(f"  Size: {pos.get('size')}")
        print(f"  Entry Price: {pos.get('entry_price')}")
        print(f"  Close Price: {pos.get('current_price') or pos.get('exit_price')}")
        print(f"  Rule Code: {pos.get('rule_code')}")
        print(f"  Close Reason: {pos.get('close_reason')}")
        print(f"  Closed At: {pos.get('closed_at')}")
        print(f"  Created At: {pos.get('created_at')}")
        print(f"  Realized PnL: {pos.get('realized_pnl')}")
        print("-" * 50)

if __name__ == "__main__":
    check_sol_positions()
