import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from app.core.supabase_client import get_supabase

async def test_rpcs():
    sys.stdout.reconfigure(encoding='utf-8')
    sb = get_supabase()
    print("=== TESTING RPC FUNCTIONS IN DATABASE ===")
    
    query = "ALTER TABLE watchlist_daily ADD COLUMN IF NOT EXISTS margin_of_safety NUMERIC DEFAULT 0;"
    
    # Try different RPC function names
    rpcs = ['exec_sql_return', 'exec_sql', 'query_db', 'run_sql', 'execute_sql']
    params = ['sql_text', 'sql_query', 'query', 'sql', 'query_text']
    
    for rpc in rpcs:
        print(f"\n--- Testing RPC: {rpc} ---")
        for param in params:
            try:
                res = sb.rpc(rpc, {param: query}).execute()
                print(f"  ✅ SUCCESS using sb.rpc('{rpc}', {{{param}: ...}})")
                print(f"  Result: {res.data}")
                return
            except Exception as e:
                # Check if it was a function-not-found error or something else
                e_str = str(e)
                if "Could not find the function" in e_str:
                    pass
                else:
                    print(f"  Returned other error for param '{param}': {e_str}")

if __name__ == "__main__":
    asyncio.run(test_rpcs())
