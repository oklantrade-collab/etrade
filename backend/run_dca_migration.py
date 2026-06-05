import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from supabase import create_client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    sql = """
    ALTER TABLE public.positions 
    ADD COLUMN IF NOT EXISTS dca_executed BOOLEAN DEFAULT FALSE;
    """
    
    try:
        sb.rpc("exec_sql", {"sql_text": sql}).execute()
        print("[OK] Migration 032 applied via RPC")
    except Exception as e:
        print(f"[INFO] RPC not available ({e}), checking if column exists...")
        try:
            res = sb.table("positions").select("dca_executed").limit(1).execute()
            print("[OK] Column dca_executed already exists")
        except Exception as e2:
            print(f"[WARNING] Column may not exist: {e2}")

if __name__ == "__main__":
    main()
