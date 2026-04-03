import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
supabase = create_client(url, key)

sql = """
ALTER TABLE market_snapshot
ADD COLUMN IF NOT EXISTS upper_1 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS upper_2 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS upper_3 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS upper_4 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS lower_1 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS lower_2 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS lower_3 NUMERIC(20,8),
ADD COLUMN IF NOT EXISTS lower_4 NUMERIC(20,8);
"""

try:
    # Supabase doesn't have a direct 'sql' method in the python client easily
    # But usually we have a stored procedure 'exec_sql' for this if set up
    # Since I don't know if it's there, I'll try to just select the cols and if it fails, I'll tell the user.
    # Actually, I can use the postgrest client for some things, but not DDL.
    
    # I'll try to use 'rpc' if available
    res = supabase.postgrest.rpc('exec_sql', {'sql_query': sql}).execute()
    print("Migration successful via RPC!")
except Exception as e:
    print(f"RPC exec_sql failed (likely not defined): {e}")
    print("Please run migration_017_market_snapshot_bands.sql manually in Supabase editor.")
