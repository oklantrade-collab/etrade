import sys
import io

# Force UTF-8 for windows console
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('system_logs').select('message, created_at').order('created_at', desc=True).limit(500).execute()
found = False
for l in res.data:
    msg = l['message']
    if any(k in msg for k in ['SYMBOL_LIMIT', 'ATOMIC BLOCK', 'BLOCK']):
        print(f"{l['created_at']}: {msg}")
        found = True
if not found:
    print("No limit logs found in last 500 entries.")
