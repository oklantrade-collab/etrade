
import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.core.supabase_client import get_supabase

def fix_schema():
    sb = get_supabase()
    
    queries = [
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS stop_loss NUMERIC;",
        "ALTER TABLE stocks_positions ADD COLUMN IF NOT EXISTS take_profit NUMERIC;",
        "ALTER TABLE stocks_positions DROP CONSTRAINT IF EXISTS stocks_positions_ticker_status_key;",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_stocks_positions_ticker_open ON stocks_positions (ticker) WHERE (status = 'open');"
    ]
    
    print("Adding stop_loss and take_profit columns to stocks_positions...")
    
    for i, query in enumerate(queries):
        try:
            # Trying 'exec_sql' with the correct parameter name 'sql_query'
            sb.rpc('exec_sql', {'sql_query': query}).execute()
            print(f"  OK: Query {i+1} executed.")
        except Exception as e:
            print(f"  ERR: Query {i+1} failed: {e}")
            print(f"  Attempting variation 'query' instead of 'sql_query'...")
            try:
                sb.rpc('exec_sql', {'query': query}).execute()
                print(f"  OK: Query {i+1} executed with 'query' param.")
            except Exception as e2:
                print(f"  ERR: Query {i+1} failed with 'query' param too: {e2}")

if __name__ == "__main__":
    fix_schema()
