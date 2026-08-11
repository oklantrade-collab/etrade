import os
import sys
import dotenv

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

payload = {
    "name": "LONG scalp SAR 15m cambió + Pine Buy",
    "min_score": 0.9,
    "confidence": 0.8,
    "cycle": "5m",
    "applicable_cycles": ["5m", "15m"],
    "condition_ids": [209, 208, 9926, 9922, 20, 11],
    "condition_weights": {
        "209": 0.2,
        "208": 0.2,
        "9926": 0.3,
        "9922": 0.1,
        "20": 0.1,
        "11": 0.1
    },
    "notes": "SAR 15m cambió a alcista + PineScript Buy | Modificado para evitar retroceso (agregado EMA20)"
}

res = sb.table("strategy_rules_v2").update(payload).eq("rule_code", "Aa23").execute()
print("UPDATED Aa23 IN SUPABASE strategy_rules_v2:")
import json
print(json.dumps(res.data, indent=2))
