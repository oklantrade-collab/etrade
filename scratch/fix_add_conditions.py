import os
import sys
import dotenv
import json

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

res_v = sb.table("strategy_variables").select("id").order("id", desc=True).limit(1).execute()
max_v_id = res_v.data[0]["id"] if res_v.data else 200
print(f"MAX VARIABLE ID: {max_v_id}")

res_c = sb.table("strategy_conditions").select("id").order("id", desc=True).limit(1).execute()
max_c_id = res_c.data[0]["id"] if res_c.data else 300
print(f"MAX CONDITION ID: {max_c_id}")

# Variable 1
v1_id = max_v_id + 1
var_lower = {
    "id": v1_id,
    "name": "close_below_bb_lower_5m",
    "category": "combined",
    "timeframes": ["5m"],
    "data_type": "boolean",
    "description": "Close por debajo de la Banda Inferior de Bollinger en 5m",
    "source_field": "close_below_bb_lower_5m",
    "enabled": True
}
# Variable 2
v2_id = max_v_id + 2
var_upper = {
    "id": v2_id,
    "name": "close_above_bb_upper_5m",
    "category": "combined",
    "timeframes": ["5m"],
    "data_type": "boolean",
    "description": "Close por encima de la Banda Superior de Bollinger en 5m",
    "source_field": "close_above_bb_upper_5m",
    "enabled": True
}

sb.table("strategy_variables").insert(var_lower).execute()
print(f"INSERTED VARIABLE {v1_id}")

sb.table("strategy_variables").insert(var_upper).execute()
print(f"INSERTED VARIABLE {v2_id}")

c1_id = max_c_id + 1
cond_lower = {
    "id": c1_id,
    "name": "CLOSE < BANDA INFERIOR BOLLINGER 5M",
    "variable_id": v1_id,
    "operator": "==",
    "value_type": "literal",
    "value_literal": 1,
    "timeframe": "5m",
    "description": "CLOSE < BANDA INFERIOR BOLLINGER en temporalidad de 5 minutos",
    "enabled": True
}

c2_id = max_c_id + 2
cond_upper = {
    "id": c2_id,
    "name": "CLOSE > BANDA SUPERIOR BOLLINGER 5M",
    "variable_id": v2_id,
    "operator": "==",
    "value_type": "literal",
    "value_literal": 1,
    "timeframe": "5m",
    "description": "CLOSE > BANDA SUPERIOR BOLLINGER en temporalidad de 5 minutos",
    "enabled": True
}

sb.table("strategy_conditions").insert(cond_lower).execute()
print(f"INSERTED CONDITION {c1_id}: CLOSE < BANDA INFERIOR BOLLINGER 5M")

sb.table("strategy_conditions").insert(cond_upper).execute()
print(f"INSERTED CONDITION {c2_id}: CLOSE > BANDA SUPERIOR BOLLINGER 5M")
