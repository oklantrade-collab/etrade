import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def inspect():
    sb = get_supabase()
    
    print("=== positions keys ===")
    try:
        res = sb.table('positions').select('*').limit(1).execute()
        if res.data:
            print("Keys:", sorted(res.data[0].keys()))
            # Print sample
            p = res.data[0]
            print(f"Sample - ID: {p.get('id')} | Symbol: {p.get('symbol')} | Status: {p.get('status')} | PnL: {p.get('realized_pnl') or p.get('pnl')}")
        else:
            print("No rows in positions.")
    except Exception as e:
        print(f"Error: {e}")
        
    print("\n=== forex_positions keys ===")
    try:
        res = sb.table('forex_positions').select('*').limit(1).execute()
        if res.data:
            print("Keys:", sorted(res.data[0].keys()))
            p = res.data[0]
            print(f"Sample - ID: {p.get('id')} | Symbol: {p.get('symbol')} | Status: {p.get('status')} | Lots: {p.get('lots')}")
        else:
            print("No rows in forex_positions.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect()
