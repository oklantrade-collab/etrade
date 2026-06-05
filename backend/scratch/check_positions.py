import os
import sys
import pandas as pd
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from app.core.supabase_client import get_supabase

def check_positions():
    sb = get_supabase()
    res = sb.table('positions')\
        .select('*')\
        .eq('symbol', 'BTCUSDT')\
        .order('opened_at', desc=True)\
        .limit(10)\
        .execute()
    
    df = pd.DataFrame(res.data or [])
    if not df.empty:
        print("=== BTCUSDT Positions (Last 10) ===")
        for idx, row in df.iterrows():
            opened_utc = datetime.fromisoformat(row['opened_at'].replace('Z', '+00:00'))
            opened_local = opened_utc.astimezone(timezone(timedelta(hours=-5)))
            
            closed_local_str = "OPEN"
            if row.get('closed_at'):
                closed_utc = datetime.fromisoformat(row['closed_at'].replace('Z', '+00:00'))
                closed_local = closed_utc.astimezone(timezone(timedelta(hours=-5)))
                closed_local_str = closed_local.strftime('%Y-%m-%d %H:%M:%S')
                
            print(f"ID: {row['id']} | Rule: {row['rule_code']} | Status: {row['status']}")
            print(f"  Opened: {opened_local.strftime('%Y-%m-%d %H:%M:%S')} | Closed: {closed_local_str}")
            print(f"  Entry: {row['entry_price']} | Avg Entry: {row['avg_entry_price']} | Close: {row.get('close_price')} | PNL: {row.get('realized_pnl')}")
            print(f"  Reason: {row.get('close_reason')} | EREP Active: {row.get('erep_active')} | EREP Target Price: {row.get('erep_target_price')}")
            print("-" * 50)

if __name__ == "__main__":
    check_positions()
