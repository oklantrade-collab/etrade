import os
import json
from supabase import create_client
from dotenv import load_dotenv

# Load .env from backend
load_dotenv('backend/.env')

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

res = sb.table('forex_positions').select('*').order('closed_at', desc=True).limit(10).execute()
print(json.dumps(res.data, indent=2))
