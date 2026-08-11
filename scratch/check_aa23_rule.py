import os
import sys
import dotenv
import json

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res = sb.table("strategy_rules_v2").select("*").eq("rule_code", "Aa23").execute()
print("STRATEGY_RULES_V2 FOR Aa23:")
print(json.dumps(res.data, indent=2))
