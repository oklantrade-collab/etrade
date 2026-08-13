import os
env_vars = {}
with open('backend/.env') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1)
            env_vars[k.strip()] = v.strip().strip('"\'')

url = env_vars.get('NEXT_PUBLIC_SUPABASE_URL')
key = env_vars.get('SUPABASE_SERVICE_ROLE_KEY')

from supabase import create_client
sb = create_client(url, key)
res = sb.table('forex_positions').select('id, symbol, rule_code, sl_price, tp_price, status').eq('status', 'open').execute()
for pos in res.data:
    print(pos)
