import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Load environment
load_dotenv('c:/Fuentes/eTrade/backend/.env')

sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== TRADING CONFIG ===")
try:
    res = sb.table('trading_config').select('*').execute()
    for row in res.data:
        for k, v in row.items():
            print(f"  {k}: {v}")
except Exception as e:
    print("Error querying trading_config:", e)

print("\n=== RISK CONFIG ===")
try:
    res = sb.table('risk_config').select('*').execute()
    for row in res.data:
        for k, v in row.items():
            print(f"  {k}: {v}")
except Exception as e:
    print("Error querying risk_config:", e)
