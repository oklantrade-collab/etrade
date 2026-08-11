import os
import sys
import dotenv
import json

dotenv.load_dotenv("c:/Fuentes/eTrade/backend/.env")
sys.path.append("c:/Fuentes/eTrade/backend")

from app.core.supabase_client import get_supabase
sb = get_supabase()

# 1. Variables
var_lower = {
    "name": "close_below_bb_lower_5m",
    "category": "combined",
    "timeframes": ["5m"],
    "data_type": "boolean",
    "description": "Close por debajo de la Banda Inferior de Bollinger en 5m",
    "source_field": "close_below_bb_lower_5m",
    "enabled": True
}
var_upper = {
    "name": "close_above_bb_upper_5m",
    "category": "combined",
    "timeframes": ["5m"],
    "data_type": "boolean",
    "description": "Close por encima de la Banda Superior de Bollinger en 5m",
    "source_field": "close_above_bb_upper_5m",
    "enabled": True
}

# Consultar si existen
ex_lower = sb.table("strategy_variables").select("*").eq("source_field", "close_below_bb_lower_5m").execute()
if not ex_lower.data:
    res_l = sb.table("strategy_variables").insert(var_lower).execute()
    var_lower_id = res_l.data[0]["id"]
    print("VARIABLE CREADA:", res_l.data[0])
else:
    var_lower_id = ex_lower.data[0]["id"]
    print("VARIABLE EXISTENTE:", ex_lower.data[0])

ex_upper = sb.table("strategy_variables").select("*").eq("source_field", "close_above_bb_upper_5m").execute()
if not ex_upper.data:
    res_u = sb.table("strategy_variables").insert(var_upper).execute()
    var_upper_id = res_u.data[0]["id"]
    print("VARIABLE CREADA:", res_u.data[0])
else:
    var_upper_id = ex_upper.data[0]["id"]
    print("VARIABLE EXISTENTE:", ex_upper.data[0])

# 2. Condiciones
cond_lower = {
    "name": "CLOSE < BANDA INFERIOR BOLLINGER 5M",
    "variable_id": var_lower_id,
    "operator": "==",
    "value_type": "literal",
    "value_literal": 1,
    "timeframe": "5m",
    "description": "CLOSE < BANDA INFERIOR BOLLINGER en temporalidad de 5 minutos",
    "enabled": True
}

cond_upper = {
    "name": "CLOSE > BANDA SUPERIOR BOLLINGER 5M",
    "variable_id": var_upper_id,
    "operator": "==",
    "value_type": "literal",
    "value_literal": 1,
    "timeframe": "5m",
    "description": "CLOSE > BANDA SUPERIOR BOLLINGER en temporalidad de 5 minutos",
    "enabled": True
}

ex_c_lower = sb.table("strategy_conditions").select("*").eq("name", "CLOSE < BANDA INFERIOR BOLLINGER 5M").execute()
if not ex_c_lower.data:
    res_cl = sb.table("strategy_conditions").insert(cond_lower).execute()
    print("CONDICION CREADA:", res_cl.data[0])
else:
    print("CONDICION EXISTENTE:", ex_c_lower.data[0])

ex_c_upper = sb.table("strategy_conditions").select("*").eq("name", "CLOSE > BANDA SUPERIOR BOLLINGER 5M").execute()
if not ex_c_upper.data:
    res_cu = sb.table("strategy_conditions").insert(cond_upper).execute()
    print("CONDICION CREADA:", res_cu.data[0])
else:
    print("CONDICION EXISTENTE:", ex_c_upper.data[0])
