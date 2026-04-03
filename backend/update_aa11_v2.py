
from app.core.supabase_client import get_supabase
sb = get_supabase()

# 1. Crear Variable ID 54
var_payload = {
    "id": 54,
    "name": "Mercado Lateral o Basis Subiendo",
    "category": "combined",
    "timeframes": ["15m", "4h"],
    "data_type": "boolean",
    "description": "Indica si el mercado es lateral o el basis está subiendo (slope > 0)",
    "source_field": "is_range_or_rise",
    "enabled": True
}
try:
    sb.table("strategy_variables").upsert(var_payload).execute()
    print("Variable 54 upserted.")
except Exception as e:
    print(f"Failed to upsert Variable: {e}")

# 2. Crear Condición ID 54
cond_payload = {
    "id": 54,
    "variable_id": 54,
    "name": "Range o Basis UP (OR)",
    "operator": "==",
    "value_type": "literal",
    "value_literal": 1, 
    "timeframe": "15m",
    "description": "Se cumple si el mercado es lateral O si el basis está subiendo",
    "enabled": True
}
try:
    sb.table("strategy_conditions").upsert(cond_payload).execute()
    print("Condition 54 upserted.")
except Exception as e:
    print(f"Failed to upsert Condition: {e}")

# 3. Actualizar Regla Aa11
rule_code = "Aa11"
rule_res = sb.table("strategy_rules_v2").select("*").eq("rule_code", rule_code).single().execute()
rule = rule_res.data

if rule:
    # Eliminar: 11 (EMA20 angle), 6 (+DI cross), 24 (SAR 15m)
    # Mantener: 1 (ADX), 26 (SAR 4h), 40 (Structure)
    # Agregar: 36 (Pine Buy), 54 (Range/Rise)
    
    new_ids = [1, 26, 40, 36, 54]
    new_weights = {
        "1": 0.20,      # ADX < 20
        "26": 0.15,     # SAR 4h
        "40": 0.10,     # Structure
        "36": 0.20,     # Pine Buy
        "54": 0.35      # Range/Rise (OR)
    }
    
    update_data = {
        "name": "LONG Aa11: Pine Buy + Range/Rise + Bullish MTF",
        "condition_ids": new_ids,
        "condition_weights": new_weights,
        "notes": "Actualizada: Eliminadas EMAs y DI; agregados PineScript Buy y Range/Basis UP (OR)",
        "min_score": 0.65 # Subimos un poco para mayor calidad
    }
    
    res = sb.table("strategy_rules_v2").update(update_data).eq("rule_code", rule_code).execute()
    print(f"Rule {rule_code} updated successfully.")
else:
    print(f"Rule {rule_code} not found.")
