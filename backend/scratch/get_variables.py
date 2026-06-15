import os
import sys
import json
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv("c:/Fuentes/eTrade/backend/.env")

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(url, key)

res = supabase.table('strategy_variables').select('*').execute()
print(json.dumps(res.data, indent=2))
