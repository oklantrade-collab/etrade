
import os
import sys
from datetime import datetime, timedelta, timezone
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def aggressive_cleanup():
    sb = get_supabase()
    
    # 1. system_logs: 12 hours instead of 48
    cutoff_logs = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
    print(f"Purging system_logs older than {cutoff_logs}...")
    res_logs = sb.table("system_logs").delete().lt("created_at", cutoff_logs).execute()
    deleted_logs = len(res_logs.data) if res_logs.data else 0
    print(f"Deleted {deleted_logs} logs.")

    # 2. technical_indicators / technical_scores: 1 day
    cutoff_tech = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    print(f"Purging technical_scores older than {cutoff_tech}...")
    res_tech = sb.table("technical_scores").delete().lt("timestamp", cutoff_tech).execute()
    deleted_tech = len(res_tech.data) if res_tech.data else 0
    print(f"Deleted {deleted_tech} tech scores.")

    # 3. strategy_evaluations: 2 days
    cutoff_evals = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    print("Purging strategy_evaluations...")
    res_evals = sb.table("strategy_evaluations").delete().lt("created_at", cutoff_evals).execute()
    deleted_evals = len(res_evals.data) if res_evals.data else 0
    print(f"Deleted {deleted_evals} evaluations.")

    print("--- CLEANUP FINISHED ---")
    print(f"Total rows freed: {deleted_logs + deleted_tech + deleted_evals}")

if __name__ == "__main__":
    aggressive_cleanup()
