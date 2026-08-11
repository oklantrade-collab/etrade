import os
import sys
import dotenv
import json

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res_vars = sb.table("strategy_variables").select("*").execute()
print("STRATEGY VARIABLES FOR CLOSE AND BOLLINGER:")
for v in res_vars.data or []:
    name = (v.get('name') or '').lower()
    field = (v.get('source_field') or '').lower()
    if 'close' in name or 'close' in field or 'bb' in name or 'bb' in field or 'band' in name or 'band' in field or 'lower' in name or 'upper' in name:
        print(v)
