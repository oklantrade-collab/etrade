import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def apply_migration():
    sb = get_supabase()
    
    tables = ['positions', 'forep_positions', 'stocks_positions']
    # Wait, the table for Forex is forex_positions, not forep_positions. Let's fix that.
    tables = ['positions', 'forex_positions', 'stocks_positions']
    
    # We will define a general list of column definitions to add to all three tables
    columns = [
        ("erep_active", "BOOLEAN DEFAULT false"),
        ("erep_phase", "INTEGER DEFAULT 0"),
        ("erep_p1_price", "NUMERIC"),
        ("erep_p1_size", "NUMERIC"),
        ("erep_p2_price", "NUMERIC"),
        ("erep_p2_size", "NUMERIC"),
        ("erep_p3_avg", "NUMERIC"),
        ("erep_target_price", "NUMERIC"),
        ("erep_target_band", "VARCHAR(20)"),
        ("erep_target_band_price", "NUMERIC"),
        ("erep_target_95pct", "NUMERIC"),
        ("erep_q1", "NUMERIC"),
        ("erep_q2_calculated", "NUMERIC"),
        ("erep_q2_rounded", "NUMERIC"),
        ("erep_p3_recalculated", "NUMERIC"),
        ("erep_max_loss_pct", "NUMERIC DEFAULT 8.0"),
        ("erep_timeout_cycles", "INTEGER DEFAULT 6"),
        ("erep_cycles_elapsed", "INTEGER DEFAULT 0"),
        ("erep_activated_at", "TIMESTAMPTZ"),
        ("erep_close_reason", "VARCHAR(50)"),
        ("erep_market_type", "VARCHAR(20)")
    ]
    
    queries = []
    for table in tables:
        for col_name, col_type in columns:
            queries.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type};")

    print(f"Applying EREP migration on {len(tables)} tables...")
    for q in queries:
        try:
            print(f"Executing: {q}")
            sb.rpc('exec_sql', {'sql_text': q}).execute()
            print("  OK")
        except Exception as e:
            print(f"  Error/Warning: {e}")

    # Verification Query
    verify_query = """
    SELECT table_name, column_name, data_type 
    FROM information_schema.columns 
    WHERE column_name LIKE 'erep_%' 
    ORDER BY table_name, column_name;
    """
    print("\nVerifying added EREP columns:")
    try:
        res = sb.rpc('exec_sql', {'sql_text': verify_query}).execute()
        if res.data:
            print(f"{'Table Name':<20} | {'Column Name':<25} | {'Data Type'}")
            print("-" * 60)
            for row in res.data:
                print(f"{row.get('table_name'):<20} | {row.get('column_name'):<25} | {row.get('data_type')}")
        else:
            print("No EREP columns found in the schema.")
    except Exception as e:
        print(f"Verification failed: {e}")

if __name__ == "__main__":
    apply_migration()
