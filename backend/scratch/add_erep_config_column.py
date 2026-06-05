import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Cargar variables de entorno
load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')

if not url or not key:
    print("Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not found in environment.")
    sys.exit(1)

sb = create_client(url, key)

# Query SQL para añadir la columna erep_max_purchases con default de 5
sql = """
ALTER TABLE trading_config ADD COLUMN IF NOT EXISTS erep_max_purchases integer DEFAULT 5;
UPDATE trading_config SET erep_max_purchases = 5 WHERE erep_max_purchases IS NULL;
"""

print("Executing DDL migration on Supabase...")
try:
    res = sb.postgrest.rpc('exec_sql', {'sql_query': sql}).execute()
    print("Migration successful! Column 'erep_max_purchases' has been added to 'trading_config' with default 5.")
    
    # Verificar leyendo la config de nuevo
    verify = sb.table("trading_config").select("erep_max_purchases").eq("id", 1).maybe_single().execute()
    if verify.data:
        print(f"Verified value in database: {verify.data}")
    else:
        print("Verification warning: could not read back row with id=1.")
except Exception as e:
    print(f"Failed to execute migration via RPC: {e}")
    sys.exit(1)
