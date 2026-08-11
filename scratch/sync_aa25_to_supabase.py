import os
import sys
import dotenv

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

payload = {
    "name": "LONG Cruce EMA3 > EMA9 en Tendencia",
    "min_score": 0.8,
    "confidence": 0.8,
    "cycle": "5m",
    "applicable_cycles": ["5m"],
    "condition_weights": {
        "223": 0.3,
        "224": 0.1,
        "218": 0.4,
        "220": 0.2
    },
    "notes": "Cruce EMA3>EMA9 validando tendencia con EMA20"
}

res = sb.table("strategy_rules_v2").update(payload).eq("rule_code", "Aa25").execute()
print("UPDATED Aa25 IN SUPABASE strategy_rules_v2:")
import json
print(json.dumps(res.data, indent=2))
