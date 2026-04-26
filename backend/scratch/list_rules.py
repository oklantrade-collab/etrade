import sys
import json
from app.core.supabase_client import get_supabase

sb = get_supabase()
res = sb.table('trading_rules').select('*').execute()
for r in res.data:
    print(json.dumps(r, indent=2, ensure_ascii=False))
