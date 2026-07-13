import os
import sys
from datetime import datetime, timedelta, timezone
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from app.workers.data_cleanup import cleanup_database
import time

def delete_in_batches(sb, table_name, time_col, cutoff, batch_size=100):
    total_deleted = 0
    print(f"Purging {table_name} older than {cutoff} in batches of {batch_size}...")
    
    while True:
        try:
            # Seleccionar IDs a borrar
            sel_res = sb.table(table_name).select("id").lt(time_col, cutoff).limit(batch_size).execute()
            if not sel_res.data:
                break
                
            ids = [row["id"] for row in sel_res.data]
            
            # Borrar esos IDs
            del_res = sb.table(table_name).delete().in_("id", ids).execute()
            deleted = len(del_res.data) if del_res.data else 0
            total_deleted += deleted
            print(f"  ... deleted batch of {deleted} rows from {table_name}. Total so far: {total_deleted}")
            
            if len(ids) < batch_size:
                break
                
            time.sleep(0.5) # Pausa para no sobrecargar la DB
        except Exception as e:
            print(f"Error while batch deleting {table_name}: {e}")
            break
            
    return total_deleted

def aggressive_cleanup():
    sb = get_supabase()
    print("--- STARTING BATCHED AGGRESSIVE MANUAL PURGE ---")

    # 1. strategy_evaluations: 1 day
    cutoff_evals = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    delete_in_batches(sb, "strategy_evaluations", "created_at", cutoff_evals)

    # 2. apex_scores: 1 day
    cutoff_apex = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    delete_in_batches(sb, "apex_scores", "calculated_at", cutoff_apex)

    # 3. candle_patterns: 1 day
    cutoff_patterns = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    delete_in_batches(sb, "candle_patterns", "timestamp", cutoff_patterns)
    
    # 4. context_scores: 1 day
    cutoff_ctx = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    delete_in_batches(sb, "context_scores", "date", cutoff_ctx)

    # 5. technical_scores: 1 day
    cutoff_tech = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    delete_in_batches(sb, "technical_scores", "timestamp", cutoff_tech)

    print("\n--- RUNNING MAIN DATA CLEANUP ROUTINE (for market_candles) ---")
    import asyncio
    results = asyncio.run(cleanup_database())
    print("Main cleanup results:", results)

if __name__ == "__main__":
    aggressive_cleanup()
