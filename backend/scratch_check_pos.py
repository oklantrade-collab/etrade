import os
import sys
from supabase import create_client

# Carga manual del .env
def load_env():
    root_dir = os.path.abspath(os.path.join(os.getcwd()))
    dotenv_path = os.path.join(root_dir, '.env')
    if os.path.exists(dotenv_path):
        with open(dotenv_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                os.environ[key.strip()] = value.strip().strip('"').strip("'")

load_env()
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

res = sb.table('forex_positions').select('*').execute()
print(f"Total positions in forex_positions: {len(res.data)}")
for p in res.data:
    print(f"ID: {p.get('id')}, Symbol: {p.get('symbol')}, PnL: {p.get('realized_pnl') or p.get('unrealized_pnl')}")
