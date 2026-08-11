import os
import sys
import dotenv

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

payload = {
    "name": "LONG HOT Momentum",
    "min_score": 0.9,
    "confidence": 0.8,
    "cycle": "15m",
    "applicable_cycles": ["5m", "15m"],
    "condition_ids": [74, 223, 36, 218, 75],
    "condition_weights": {
        "74": 0.2,
        "223": 0.3,
        "36": 0.1,
        "218": 0.3,
        "75": 0.1
    },
    "notes": "HOT Momentum alcista C: Cruce EMA3>EMA9 (40%) + EMA20 Ascendiendo 1h (20%) + PineScript Buy (40%)"
}

res = sb.table("strategy_rules_v2").update(payload).eq("rule_code", "AaHotC").execute()
print("UPDATED AaHotC IN SUPABASE strategy_rules_v2:")
import json
print(json.dumps(res.data, indent=2))
