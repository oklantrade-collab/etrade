"""
Apply Migration 027: Candle Signals Table
Creates the candle_signals audit table for the ANTIGRAVITY Candle Signal Validator.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Read and execute SQL migration
    sql_path = os.path.join(os.path.dirname(__file__), "migration_027_candle_signals.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    
    # Execute via RPC (Supabase doesn't support multi-statement SQL directly)
    # We'll create the table using individual statements
    try:
        sb.rpc("exec_sql", {"sql_text": sql}).execute()
        print("[OK] Migration 027 applied via RPC")
    except Exception as e:
        # Fallback: try table creation check
        print(f"[INFO] RPC not available ({e}), checking if table exists...")
        try:
            res = sb.table("candle_signals").select("id").limit(1).execute()
            print("[OK] Table candle_signals already exists")
        except Exception as e2:
            print(f"[WARNING] Table candle_signals may not exist: {e2}")
            print("[ACTION] Please run the SQL in migration_027_candle_signals.sql manually in the Supabase SQL Editor")

if __name__ == "__main__":
    main()
