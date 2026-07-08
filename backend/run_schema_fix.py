import os
import sys
import asyncio
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

async def run_migration():
    import io
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        
    sb = get_supabase()
    print("=== RUNNING DATABASE SCHEMA FIX MIGRATION ===")
    
    queries = [
        "ALTER TABLE paper_trades ALTER COLUMN rule_code TYPE VARCHAR(50);",
        "ALTER TABLE positions ALTER COLUMN close_reason TYPE VARCHAR(100);",
        "ALTER TABLE forex_positions ALTER COLUMN close_reason TYPE VARCHAR(100);",
        "ALTER TABLE stocks_positions ALTER COLUMN close_reason TYPE VARCHAR(100);"
    ]
    
    rpcs = ['exec_sql', 'exec_sql_return', 'query_db', 'run_sql', 'execute_sql']
    params = ['sql_query', 'sql_text', 'query', 'sql', 'query_text']
    
    for query in queries:
        print(f"\nExecuting: {query}")
        success = False
        for rpc in rpcs:
            for param in params:
                try:
                    res = sb.rpc(rpc, {param: query}).execute()
                    print(f"  ✅ SUCCESS using sb.rpc('{rpc}', {{{param}: ...}})")
                    success = True
                    break
                except Exception as e:
                    e_str = str(e)
                    if "Could not find the function" in e_str:
                        continue
                    else:
                        print(f"  Failed with rpc '{rpc}' param '{param}': {e_str}")
            if success:
                break
        if not success:
            print(f"  ❌ FAILED to execute query: {query}")

if __name__ == "__main__":
    asyncio.run(run_migration())
