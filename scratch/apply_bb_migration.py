import os
import sys
# Add backend to PYTHONPATH
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

from app.core.supabase_client import get_supabase

def apply_migration():
    sb = get_supabase()
    
    tables = ['positions', 'forex_positions']
    
    queries = []
    for table in tables:
        queries.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS bb_touched BOOLEAN DEFAULT false;")
        queries.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS ts_state JSONB DEFAULT '{{}}'::jsonb;")

    print(f"Applying BB Touch migration on {len(tables)} tables...")
    for q in queries:
        try:
            print(f"Executing: {q}")
            sb.rpc('exec_sql', {'sql_text': q}).execute()
            print("  OK")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    apply_migration()
