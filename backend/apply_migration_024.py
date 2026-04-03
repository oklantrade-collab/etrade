import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def apply_migration():
    sb = get_supabase()
    migration_file = Path(__file__).parent / 'migration_024_auth_system.sql'
    
    if not migration_file.exists():
        print(f"❌ Migration file not found: {migration_file}")
        return

    with open(migration_file, 'r', encoding='utf-8') as f:
        sql = f.read()

    print("Applying Migration 024 (Auth & Admin System)...")
    
    # Supabase RPC 'exec_sql' often limits to single queries or has security restrictions.
    # We will try to split by semicolon if possible, but for CREATE TABLE blocks it's better to run carefully.
    
    # Split by segments to avoid complex transaction issues in some RPC setups
    queries = [q.strip() for q in sql.split(';') if q.strip()]
    
    for i, query in enumerate(queries):
        try:
            # We add back the semicolon for execution
            full_query = query + ";"
            sb.rpc('exec_sql', {'query': full_query}).execute()
            print(f"  OK: Query {i+1} executed successfully.")
        except Exception as e:
            print(f"  ERR: Query {i+1} failed: {e}")
            # If it fails, maybe it already exists or there's a syntax error.
            # Continue for now to see others.

    print("\n[Done] Migration 024 finished.")

if __name__ == "__main__":
    apply_migration()
