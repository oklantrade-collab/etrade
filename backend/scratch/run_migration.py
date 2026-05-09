import asyncio
import sys
import os
from app.core.supabase_client import get_supabase

async def run_migration(file_path):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        sql = f.read()

    sb = get_supabase()
    # Execute SQL via rpc if available, or just log instructions
    # Since we can't run arbitrary SQL easily via the client without a custom RPC function,
    # we'll use the 'exec_sql' RPC if it exists, otherwise we'll advise.
    try:
        res = sb.rpc("exec_sql", {"sql_query": sql}).execute()
        print(f"MIGRATION SUCCESS: {res.data}")
    except Exception as e:
        print(f"MIGRATION FAILED via RPC: {e}")
        print("Please execute the following SQL manually in Supabase SQL Editor:")
        print("-" * 40)
        print(sql)
        print("-" * 40)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_migration.py <path_to_sql>")
    else:
        asyncio.run(run_migration(sys.argv[1]))
