
from app.core.supabase_client import get_supabase
sb = get_supabase()

# 1. Variable ID 53 (Ya funciona pero lo repetimos)
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
sb.table("strategy_variables").upsert(var_payload).execute()

# 2. Condición ID 53 (Corregido: value_literal = 1)
cond_payload = {
    "id": 53,
    "variable_id": 53,
    "name": "Range o Basis Fall (OR)",
    "operator": "==",
    "value_type": "literal",
    "value_literal": 1, # Usar 1 para booleano en columna numérica de Supabase
    "timeframe": "15m",
    "description": "Se cumple si el mercado es lateral O si el basis está cayendo",
    "enabled": True
}
try:
    sb.table("strategy_conditions").upsert(cond_payload).execute()
    print("Condition 53 upserted with value 1.")
except Exception as e:
    print(f"Failed to upsert Condition: {e}")

# 3. Reload everything
# (No hace falta actualizar la regla de nuevo, ya apunta a 53)
print("Done.")
