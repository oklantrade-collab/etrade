import sys
import os

root_dir = 'c:/Fuentes/eTrade'
sys.path.insert(0, root_dir)
sys.path.insert(0, 'c:/Fuentes/eTrade/backend')

dotenv_path = os.path.join(root_dir, 'backend', '.env')
with open(dotenv_path, 'rb') as f:
    raw = f.read()
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        content = raw.decode('utf-16')
    else:
        content = raw.decode('utf-8', errors='ignore')
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k, v = k.strip(), v.strip()
        if v and v[0] in ('"', "'") and v[-1] == v[0]:
            v = v[1:-1]
        os.environ[k] = v

from supabase import create_client
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

res_open = sb.table('forex_positions').select('*').eq('status', 'open').execute()
print("=== POSICIONES ABIERTAS EN SUPABASE ===")
print("Total abiertas:", len(res_open.data or []))
for p in (res_open.data or []):
    print(p)

res_all = sb.table('forex_positions').select('*').order('opened_at', desc=True).limit(5).execute()
print("\n=== ULTIMAS 5 POSICIONES EN SUPABASE ===")
for p in (res_all.data or []):
    print(p)
