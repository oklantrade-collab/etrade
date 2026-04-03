import os
import json
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
supabase = create_client(url, key)

def run_sql(query):
    print(f"Executing: {query}")
    try:
        # Using Supabase rpc if exec_sql is available or table operations directly
        # The user provided direct SQL updates, but I'll use the table operations to be safer
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

# STEP 1.1: Update parameter_bounds
print("\n--- PASO 1.1: Update parameter_bounds ---")
# Update Threshold Medio
res = supabase.table('parameter_bounds').update({
    'current_value': 0.35,
    'description': 'Umbral MTF para entrada. Valor bajo = más señales, salida rápida por reversión. Valor alto = menos señales, movimientos más grandes.'
}).eq('parameter_name', 'mtf_threshold_medio').execute()
print(f"Medio update: {res.data}")

# Update Threshold Bajo
res = supabase.table('parameter_bounds').update({
    'current_value': 0.25
}).eq('parameter_name', 'mtf_threshold_bajo').execute()
print(f"Bajo update: {res.data}")

# Update Threshold Alto
res = supabase.table('parameter_bounds').update({
    'current_value': 0.50
}).eq('parameter_name', 'mtf_threshold_alto').execute()
print(f"Alto update: {res.data}")

# Update min_value to 0.20 for all mtf_threshold%
res = supabase.table('parameter_bounds').update({
    'min_value': 0.20
}).ilike('parameter_name', 'mtf_threshold%').execute()
print(f"Min value update: {len(res.data)} items")

# VERIFICATION CHECK 1
print("\n--- VERIFICATION CHECK 1 ---")
check = supabase.table('parameter_bounds')\
    .select('parameter_name, current_value, min_value')\
    .ilike('parameter_name', 'mtf_threshold%')\
    .order('parameter_name')\
    .execute()
for r in check.data:
    print(f"{r['parameter_name']:20} | {r['current_value']:.2f} | {r['min_value']:.2f}")

# CAMBIO 2 - PASO 1: Update trading_config
print("\n--- CAMBIO 2 - PASO 1: Update trading_config ---")
# First add columns if they don't exist (assuming SQL via RPC if possible)
try:
    sql = """
    ALTER TABLE trading_config
    ADD COLUMN IF NOT EXISTS exit_on_signal_reversal BOOLEAN DEFAULT true,
    ADD COLUMN IF NOT EXISTS exit_mtf_threshold NUMERIC(4,2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS min_profit_exit_pct NUMERIC(5,2) DEFAULT 0.30,
    ADD COLUMN IF NOT EXISTS min_profit_exit_usd NUMERIC(8,2) DEFAULT 1.00;
    """
    supabase.rpc('exec_sql', {'query_text': sql}).execute()
    print("Columns added/verified via SQL RPC")
except Exception as e:
    print(f"Alter table might have failed or RPC not available: {e}")

# Update values for id=1
res = supabase.table('trading_config').update({
    'exit_on_signal_reversal': True,
    'exit_mtf_threshold': 0.00,
    'min_profit_exit_pct': 0.30,
    'min_profit_exit_usd': 1.00
}).eq('id', 1).execute()
print(f"Trading config update: {res.data}")

# CHECK 3: trading_config verification
print("\n--- CHECK 3: trading_config verification ---")
check = supabase.table('trading_config').select('exit_on_signal_reversal, exit_mtf_threshold, min_profit_exit_pct, min_profit_exit_usd').eq('id', 1).execute()
print(json.dumps(check.data, indent=2))
