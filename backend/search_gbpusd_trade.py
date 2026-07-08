import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def search_trade():
    sb = get_supabase()
    print("=== SEARCHING SPECIFIC GBPUSD TRADE ===")
    
    # Query paper_trades table for GBPUSD with entry price close to 1.32206
    res = sb.table('paper_trades')\
        .select('*')\
        .eq('symbol', 'GBPUSD')\
        .gte('entry_price', 1.3210)\
        .lte('entry_price', 1.3230)\
        .execute()
        
    if not res.data:
        print("No matching trade found in paper_trades.")
        return
        
    for idx, t in enumerate(res.data, 1):
        print(f"\n--- Matching Trade #{idx} ---")
        for k, v in t.items():
            print(f"{k}: {v}")

if __name__ == "__main__":
    search_trade()
