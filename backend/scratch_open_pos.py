import os
import dotenv
from supabase import create_client

root_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

res = sb.table('positions').select('*').eq('status', 'open').execute()
print("OPEN POSITIONS IN SUPABASE:")
for p in res.data:
    print(p)
