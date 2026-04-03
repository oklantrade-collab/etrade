
from app.core.supabase_client import get_supabase
sb = get_supabase()

# 1. Crear Variable ID 53
var_payload = {
    "id": 53,
    "name": "Mercado Lateral o Basis Cayendo",
    "category": "combined",
    "timeframes": ["15m", "4h"],
    "data_type": "boolean",
    "description": "Indica si el mercado es lateral o el basis está en retroceso (slope < 0)",
    "source_field": "is_range_or_fall",
    "enabled": True
}
try:
    sb.table("strategy_variables").upsert(var_payload).execute()
    print("Variable 53 upserted.")
except Exception as e:
    print(f"Failed to upsert Variable: {e}")

# 2. Crear Condición ID 53
cond_payload = {
    "id": 53,
    "variable_id": 53,
    "name": "Range o Basis Fall (OR)",
    "operator": "==",
    "value_type": "literal",
    "value_literal": "true",
    "timeframe": "15m",
    "description": "Se cumple si el mercado es lateral O si el basis está cayendo",
    "enabled": True
}
try:
    sb.table("strategy_conditions").upsert(cond_payload).execute()
    print("Condition 53 upserted.")
except Exception as e:
    print(f"Failed to upsert Condition: {e}")

# 3. Refrescar Regla Bb21
rule_res = sb.table("strategy_rules_v2").select("*").eq("rule_code", "Bb21").single().execute()
rule = rule_res.data

if rule:
    # Eliminar posibles duplicados o IDs erróneos previos
    ids = [cid for cid in rule['condition_ids'] if cid not in [46, 47]]
    if 53 not in ids:
        ids.append(53)
    
    weights = {k: v for k, v in rule['condition_weights'].items() if k not in ['46', '47']}
    weights['53'] = 0.40
    
    update_data = {
        "condition_ids": ids,
        "condition_weights": weights,
        "notes": "Actualizada: Range OR Basis Fall combinados en condición ID 53 (peso 0.40)",
    }
    
    sb.table("strategy_rules_v2").update(update_data).eq("rule_code", "Bb21").execute()
    print("Rule Bb21 updated successfully.")
else:
    print("Rule Bb21 not found.")
