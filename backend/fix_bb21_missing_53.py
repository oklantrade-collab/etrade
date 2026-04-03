
from app.core.supabase_client import get_supabase
sb = get_supabase()

# 1. Crear Variable (Dejar que el ID se genere si falla con 53)
var_name = "Mercado Lateral o Basis Cayendo"
var_source = "is_range_or_fall"

# Buscar si existe ya por nombre o source
existing_var = sb.table("strategy_variables").select("*").eq("source_field", var_source).execute().data
if existing_var:
    var_id = existing_var[0]['id']
    print(f"Variable exists with ID: {var_id}")
else:
    # Insertar sin forzar ID
    var_payload = {
        "name": var_name,
        "source_field": var_source,
        "description": "Indica si el mercado es lateral o el basis está en retroceso (slope < 0)",
        "enabled": True
    }
    res = sb.table("strategy_variables").insert(var_payload).execute()
    if res.data:
        var_id = res.data[0]['id']
        print(f"Created Variable with ID: {var_id}")
    else:
        print("Failed to create Variable.")
        exit(1)

# 2. Crear Condición
cond_name = "Range o Basis Fall (OR)"
existing_cond = sb.table("strategy_conditions").select("*").eq("variable_id", var_id).execute().data
if existing_cond:
    cond_id = existing_cond[0]['id']
    print(f"Condition exists with ID: {cond_id}")
else:
    cond_payload = {
        "variable_id": var_id,
        "name": cond_name,
        "operator": "==",
        "value_type": "literal",
        "value_literal": "true",
        "description": "Se cumple si el mercado es lateral O si el basis está cayendo",
        "enabled": True
    }
    res = sb.table("strategy_conditions").insert(cond_payload).execute()
    if res.data:
        cond_id = res.data[0]['id']
        print(f"Created Condition with ID: {cond_id}")
    else:
        print("Failed to create Condition.")
        exit(1)

# 3. Actualizar Regla Bb21
rule_res = sb.table("strategy_rules_v2").select("*").eq("rule_code", "Bb21").single().execute()
rule = rule_res.data

if rule:
    # Obtener IDs actuales (sacar los viejos si quedaron, como 53 si falló)
    old_ids = [cid for cid in rule['condition_ids'] if cid not in [46, 47, 53]]
    new_ids = old_ids + [cond_id]
    
    # Pesos
    old_weights = {k: v for k, v in rule['condition_weights'].items() if k not in ['46', '47', '53']}
    new_weights = old_weights
    new_weights[str(cond_id)] = 0.40
    
    update_data = {
        "condition_ids": new_ids,
        "condition_weights": new_weights,
        "notes": f"Actualizada: Range OR Basis Fall combinados en condición ID {cond_id} (peso 0.40)",
    }
    
    sb.table("strategy_rules_v2").update(update_data).eq("rule_code", "Bb21").execute()
    print(f"Rule Bb21 updated successfully with Condition {cond_id}.")
else:
    print("Rule Bb21 not found.")
