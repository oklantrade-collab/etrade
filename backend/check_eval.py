
import sys
import os
import pandas as pd
from datetime import datetime, timezone

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

sb = get_supabase()

def check_eval_logs():
    print("=== CHECKING RECENT ENTRY_EVAL LOGS ===")
    
    # Get last 100 eval logs
    res = sb.table('system_logs')\
        .select('*')\
        .ilike('module', 'ENTRY_EVAL')\
        .order('created_at', desc=True)\
        .limit(100)\
        .execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        # Filter symbols from message (matches "SYMBOL: ...")
        # Most of them are in the format "BTCUSDT: PASS ..."
        for _, row in df.iterrows():
            print(f"[{row['created_at']}] {row['message']}")
            
    else:
        print("No evaluation logs found.")

if __name__ == "__main__":
    check_eval_logs()
