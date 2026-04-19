import sys, os
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.supabase_client import get_supabase

sb = get_supabase()

# 1. Update Dd61_15m
print("Updating Dd61_15m...")
new_weights_15m = {
    '59': 0.40,  # LOWER_6
    '203': 0.30, # AI Opportune Buy
    '201': 0.20, # No 4h Red Candle
    '58': 0.10   # Range
}
sb.table("strategy_rules_v2").update({
    "condition_weights": new_weights_15m,
    "min_score": 0.75,
    "notes": "MEJORA PRODUCTIVA: Incremento de Min Score a 0.75. Zona 6 + AI + MTF requeridos. Reduccindolo el peso del Range."
}).eq("rule_code", "Dd61_15m").execute()

# 2. Update Dd61_4h
print("Updating Dd61_4h...")
new_weights_4h = {
    '59': 0.40,  # LOWER_6
    '36': 0.25,  # PineScript Buy
    '26': 0.20,  # SAR 4h alcista
    '58': 0.15   # Range
}
sb.table("strategy_rules_v2").update({
    "condition_weights": new_weights_4h,
    "min_score": 0.75,
    "notes": "MEJORA PRODUCTIVA: Incremento de Min Score a 0.75. Zona 6 + PS Buy + SAR alcista."
}).eq("rule_code", "Dd61_4h").execute()

print("Improvement applied successfully.")
