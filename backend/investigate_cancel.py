
import sys
import os
import pandas as pd
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

sb = get_supabase()

def investigate_cancellations():
    print("=== INVESTIGATING ORDER CANCELLATIONS ===")
    
    # Get last 10 cancelled orders
    res = sb.table('pending_orders')\
        .select('*')\
        .eq('status', 'cancelled')\
        .order('created_at', desc=True)\
        .limit(10)\
        .execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        print("\n--- RECENT CANCELLED ORDERS ---")
        cols = ['symbol', 'direction', 'status', 'created_at', 'cancelled_at', 'expires_at']
        available_cols = [c for c in cols if c in df.columns]
        print(df[available_cols])
        
        # Check logs for the time around cancellation of the most recent one
        last_o = res.data[0]
        symbol = last_o['symbol']
        cancel_time = last_o['cancelled_at']
        
        print(f"\n--- LOGS FOR {symbol} AROUND {cancel_time} ---")
        # Query logs +/- 1 minute from cancellation
        res_logs = sb.table('system_logs')\
            .select('*')\
            .eq('symbol', symbol)\
            .order('created_at', desc=True)\
            .limit(100)\
            .execute()
        
        if res_logs.data:
            for r in res_logs.data:
                # Filtering manually if needed or just showing last 20 for that symbol
                print(f"[{r['created_at']}] [{r['module']}] {r['message']}")
        else:
            print("No logs found for this symbol.")
    else:
        print("No cancelled orders found.")

if __name__ == "__main__":
    investigate_cancellations()
