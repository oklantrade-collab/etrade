import os
import sys
import dotenv
import json

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res_vars = sb.table("strategy_variables").select("*").execute()
print("STRATEGY VARIABLES:")
for v in res_vars.data or []:
    print(v)

res_conds = sb.table("strategy_conditions").select("id, name, indicator_code, operator, value, category").execute()
print("\nSTRATEGY CONDITIONS (FIRST 20):")
for c in (res_conds.data or [])[:20]:
    print(c)
