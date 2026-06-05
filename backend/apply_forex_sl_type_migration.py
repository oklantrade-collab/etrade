import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def apply_migration():
    sb = get_supabase()
    
    q = "ALTER TABLE forex_positions ADD COLUMN IF NOT EXISTS sl_type VARCHAR(50);"
    print(f"Executing: {q}")
    try:
        res = sb.rpc('exec_sql', {'sql_text': q}).execute()
        print("Migration executed successfully:", res)
    except Exception as e:
        print("Error executing migration:", e)

    # Verification Query
    verify_query = """
    SELECT table_name, column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'forex_positions' AND column_name = 'sl_type';
    """
    print("\nVerifying sl_type column in forex_positions:")
    try:
        res = sb.rpc('exec_sql', {'sql_text': verify_query}).execute()
        if res.data:
            for row in res.data:
                print(f"Table: {row.get('table_name')} | Column: {row.get('column_name')} | Type: {row.get('data_type')}")
        else:
            print("sl_type column not found in forex_positions!")
    except Exception as e:
        print(f"Verification failed: {e}")

if __name__ == "__main__":
    apply_migration()
