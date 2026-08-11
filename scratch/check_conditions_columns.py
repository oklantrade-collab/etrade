import os
import sys
import dotenv
import json

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res_conds = sb.table("strategy_conditions").select("*").limit(5).execute()
print("STRATEGY CONDITIONS COLUMNS AND SAMPLE:")
print(json.dumps(res_conds.data, indent=2))
