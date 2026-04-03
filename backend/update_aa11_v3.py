
from app.core.supabase_client import get_supabase
sb = get_supabase()

rule_code = "Aa11"
rule_res = sb.table("strategy_rules_v2").select("*").eq("rule_code", rule_code).single().execute()
rule = rule_res.data

if rule:
    # Eliminar ID 1 (ADX débil)
    # Conservar y redistribuir el resto
    new_ids = [26, 40, 36, 54]
    new_weights = {
        "26": 0.20,  # SAR 4h alcista
        "40": 0.15,  # Estructura 4h LONG ok
        "36": 0.25,  # PineScript Buy (B)
        "54": 0.40   # Range o Basis UP (OR)
    }
    
    update_data = {
        "condition_ids": new_ids,
        "condition_weights": new_weights,
        "notes": "Actualizada: Eliminado ADX; pesos redistribuidos (Range/Rise OR al 40%)",
        "min_score": 0.65
    }
    
    sb.table("strategy_rules_v2").update(update_data).eq("rule_code", rule_code).execute()
    print(f"Rule {rule_code} updated successfully.")
else:
    print(f"Rule {rule_code} not found.")
