
import sys
import os
from datetime import datetime, timezone
import pandas as pd

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

sb = get_supabase()

def check_status():
    print("=== ETRADE DIAGNOSTIC STATUS ===")
    
    # 1. Check Bot Heartbeat
    print("\n--- 1. BOT HEARTBEAT ---")
    res = sb.table("bot_state").select("*").execute()
    if res.data:
        df = pd.DataFrame(res.data)
        print(df[['symbol', 'last_15m_cycle_at', 'warmup_completed', 'warmup_bars_loaded']])
    else:
        print("No data in bot_state table.")

    # 2. Check Recent Diagnostics (Last 10 entries)
    print("\n--- 2. PILOT DIAGNOSTICS (Last 10) ---")
    res = sb.table("pilot_diagnostics").select("*").order("timestamp", desc=True).limit(10).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        cols = ['timestamp', 'symbol', 'cycle_type', 'current_price', 'entry_blocked_by', 'error_occurred']
        available_cols = [c for c in cols if c in df.columns]
        print(df[available_cols])
    else:
        print("No data in pilot_diagnostics table.")

    # 3. Check Market Snapshot (Current Indicators)
    print("\n--- 3. MARKET SNAPSHOT ---")
    res = sb.table("market_snapshot").select("*").execute()
    if res.data:
        df = pd.DataFrame(res.data)
        cols = ['symbol', 'price', 'mtf_score', 'sar_phase', 'sar_trend_4h', 'regime', 'updated_at']
        available_cols = [c for c in cols if c in df.columns]
        print(df[available_cols])
    else:
        print("No data in market_snapshot table.")

    # 4. Check Recent Evaluation Logs
    print("\n--- 4. ENTRY EVALUATION LOGS ---")
    res = sb.table("system_logs").select("*").ilike("module", "ENTRY_EVAL").order("created_at", desc=True).limit(20).execute()
    if res.data:
        for r in res.data:
            print(f"[{r['created_at']}] {r['message']}")
    else:
        print("No ENTRY_EVAL logs found.")

    # 5. Check for any Errors in Logs
    print("\n--- 5. RECENT ERRORS ---")
    res = sb.table("system_logs").select("*").eq("level", "error").order("created_at", desc=True).limit(10).execute()
    if res.data:
        for r in res.data:
            print(f"[{r['created_at']}] {r['message']}")
    else:
        print("No hard errors found in system_logs.")

if __name__ == "__main__":
    check_status()
