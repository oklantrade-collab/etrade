
import sys
import os
sys.path.append(os.getcwd())
from app.core.supabase_client import get_supabase

sb = get_supabase()
res = sb.table('positions').select('*').eq('status', 'closed').order('closed_at', desc=True).limit(20).execute()
for p in res.data:
    val = p.get('rule_code') or p.get('rule_entry')
    print(f"ID: {p['id']} | rule_code: {p.get('rule_code')} | rule_entry: {p.get('rule_entry')} | RESULT: {val}")
