
import sys
import os
sys.path.append(os.getcwd())
from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('strategy_variables').select('*').execute()
for v in res.data:
    if 'signal' in v['source_field'] or 'age' in v['source_field']:
        print(f"ID: {v['id']} | FIELD: {v['source_field']} | NAME: {v['name']}")
