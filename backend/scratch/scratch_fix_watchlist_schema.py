import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from app.core.supabase_client import get_supabase

async def run_fix():
    sys.stdout.reconfigure(encoding='utf-8')
    sb = get_supabase()
    print("=== EXECUTING SCHEMA FIX FOR WATCHLIST_DAILY ===")
    
    queries = [
        "ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS margin_of_safety NUMERIC DEFAULT 0;",
        "ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS intrinsic_value NUMERIC DEFAULT 0;",
        "ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS is_overvalued BOOLEAN DEFAULT false;",
        "ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS analyst_rating NUMERIC DEFAULT 0;"
    ]
    
    for query in queries:
        print(f"\nExecuting SQL: {query}")
        success = False
        # Try both common RPC signatures for running SQL in Supabase
        for param_name in ['sql_text', 'sql_query', 'query', 'sql']:
            try:
                res = sb.rpc('exec_sql', {param_name: query}).execute()
                print(f"  Success using parameter '{param_name}'!")
                success = True
                break
            except Exception as e:
                print(f"  Attempt with '{param_name}' failed: {e}")
                
        if not success:
            print("  ❌ Could not execute SQL query via 'exec_sql' RPC.")

if __name__ == "__main__":
    asyncio.run(run_fix())
