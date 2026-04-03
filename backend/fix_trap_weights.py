
from app.core.supabase_client import get_supabase
sb = get_supabase()

# Actualizar pesos para reglas TRAP (Dd51 y Dd61)
# Haciendo que la Zona 6 sea obligatoria (Peso 0.5 y Min Score 0.75)

trap_rules = ["Dd51_15m", "Dd51_4h", "Dd61_15m", "Dd61_4h"]

for rc in trap_rules:
    res = sb.table("strategy_rules_v2").select("*").eq("rule_code", rc).maybe_single().execute()
    rule = res.data
    if not rule:
        continue
        
    weights = rule.get("condition_weights", {})
    # Identificar la condición de zona (60 para SHORT, 59 para LONG)
    zone_id = "60" if "Dd51" in rc else "59"
    range_id = "58"
    pine_id = "61" if "Dd51" in rc else "63"
    age_id = "62" if "Dd51" in rc else "64"
    
    new_weights = {
        zone_id: 0.50,
        range_id: 0.20,
        pine_id: 0.15,
        age_id: 0.15
    }
    
    update_data = {
        "condition_weights": new_weights,
        "min_score": 0.75,
        "notes": f"Mandatorio Zona 6 (Peso 0.50). Score min 0.75. Fix entrada temprana."
    }
    
    sb.table("strategy_rules_v2").update(update_data).eq("rule_code", rc).execute()
    print(f"Rule {rc} weights updated to make Zone 6 mandatory.")

print("Done.")
