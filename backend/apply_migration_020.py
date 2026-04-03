import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

with open('c:/Fuentes/eTrade/backend/migration_020_pending_orders.sql', 'r') as f:
    sql = f.read()

try:
    res = sb.postgrest.rpc('exec_sql', {'sql_query': sql}).execute()
    print("Migration successful via RPC!")
except Exception as e:
    print(f"Failed via postgrest RPC: {e}")
    # User might need to run it manually since `exec_sql` isn't installed
    print("Please run migration_020_pending_orders.sql manually in Supabase editor.")
