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

print("Initializing 'erep_max_purchases' inside 'regime_params'...")
try:
    # 1. Obtener la fila actual de trading_config (id=1)
    res = sb.table("trading_config").select("regime_params").eq("id", 1).maybe_single().execute()
    if not res.data:
        print("Error: Row with id=1 not found in 'trading_config'.")
        sys.exit(1)
        
    params = res.data.get('regime_params') or {}
    
    # 2. Inicializar erep_max_purchases a 5 si no existe
    params['erep_max_purchases'] = params.get('erep_max_purchases', 5)
    
    # 3. Guardar de nuevo en la base de datos
    sb.table("trading_config").update({'regime_params': params}).eq("id", 1).execute()
    print(f"Success! Updated 'regime_params' in DB: {params}")
    
except Exception as e:
    print(f"Failed to update JSONB column: {e}")
    sys.exit(1)
