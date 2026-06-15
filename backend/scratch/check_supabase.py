import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv("c:/Fuentes/eTrade/frontend/.env.local")

url: str = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
key: str = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
supabase: Client = create_client(url, key)

response = supabase.table('trading_config').select('regime_params').eq('id', 1).execute()
print(json.dumps(response.data, indent=2))
