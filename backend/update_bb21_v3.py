
from app.core.supabase_client import get_supabase
sb = get_supabase()

# 1. Crear Variable
var_payload = {
    "id": 53, # Intentar usar 53
    "name": "Mercado Lateral o Basis Cayendo",
    "source_field": "is_range_or_fall",
    "description": "Indica si el mercado es lateral o el basis está en retroceso (slope < 0)",
    "enabled": True
}
try:
    sb.table("strategy_variables").insert(var_payload).execute()
except:
    # Si existe, actualizar
    sb.table("strategy_variables").update(var_payload).eq("id", 53).execute()

# 2. Crear Condición
cond_payload = {
    "id": 53, # Mismo ID por consistencia
    "variable_id": 53,
    "name": "Range o Basis Fall (OR)",
    "operator": "==",
    "value_type": "literal",
    "value_literal": "true",
    "description": "Se cumple si el mercado es lateral O si el basis está cayendo",
    "enabled": True
}
try:
    sb.table("strategy_conditions").insert(cond_payload).execute()
except:
    sb.table("strategy_conditions").update(cond_payload).eq("id", 53).execute()

# 3. Actualizar Regla Bb21
# Obtener estado actual
rule_res = sb.table("strategy_rules_v2").select("*").eq("rule_code", "Bb21").single().execute()
rule = rule_res.data

if rule:
    old_ids = rule['condition_ids']
    # Eliminar 46 (Range) y 47 (Basis Fall)
    new_ids = [cid for cid in old_ids if cid not in [46, 47]]
    new_ids.append(53)
    
    old_weights = rule['condition_weights']
    new_weights = {k: v for k, v in old_weights.items() if k not in ['46', '47']}
    new_weights['53'] = 0.40 # Suma de ambos anteriores
    
    update_data = {
        "condition_ids": new_ids,
        "condition_weights": new_weights,
        "notes": "Actualizada: Range OR Basis Fall combinados en condición ID 53 (peso 0.40)",
        "condition_logic": "AND" # Mantenemos AND para que las otras sigan siendo obligatorias
    }
    
    sb.table("strategy_rules_v2").update(update_data).eq("rule_code", "Bb21").execute()
    print("Rule Bb21 updated successfully with OR condition (ID 53).")
else:
    print("Rule Bb21 not found.")
