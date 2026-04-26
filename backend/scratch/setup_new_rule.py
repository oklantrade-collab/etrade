import json
from app.core.supabase_client import get_supabase

sb = get_supabase()

new_rule = {
    "rule_code": "HOT_SENTMARKET_BUY",
    "notes": json.dumps({
        "description": "Señal OR: PineScript 'B' O SIPV 'BUY'. Basada en SM >= 6 y F.Score >= 3. Temporada 15m.",
        "sm_min": 6.0,
        "f_score_min": 3.0,
        "sipv_signal": "BUY",
        "sipv_or_pine": True,
        "sipv_required": False # Not strictly required as single signal if OR is active
    }),
    "pine_required": False # Same here
}

try:
    print(f"Updating rule HOT_SENTMARKET_BUY to OR logic (Pine OR SIPV)")
    sb.table("stocks_rules").update(new_rule).eq("rule_code", "HOT_SENTMARKET_BUY").execute()
    print("Success")
except Exception as e:
    print(f"Error: {e}")
