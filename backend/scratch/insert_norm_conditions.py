import os
import sys
import json
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv("c:/Fuentes/eTrade/backend/.env")

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(url, key)

vars_to_insert = [
    {
        "id": 150,
        "name": "RSI 14 Pullback",
        "category": "indicators",
        "timeframes": ["15m"],
        "data_type": "number",
        "description": "RSI_14 para pullbacks",
        "source_field": "rsi_14",
        "enabled": True
    },
    {
        "id": 151,
        "name": "High Touched EMA20",
        "category": "indicators",
        "timeframes": ["15m"],
        "data_type": "boolean",
        "description": "El precio toco la EMA20",
        "source_field": "high_touched_ema20",
        "enabled": True
    },
    {
        "id": 152,
        "name": "EMA9 Below EMA20",
        "category": "indicators",
        "timeframes": ["15m"],
        "data_type": "boolean",
        "description": "EMA9 menor que EMA20 (Tendencia bajista corta)",
        "source_field": "ema9_below_ema20",
        "enabled": True
    }
]

for v in vars_to_insert:
    try:
        supabase.table('strategy_variables').upsert(v).execute()
        print(f"Upserted var {v['name']}")
    except Exception as e:
        print(f"Failed to upsert var {v['name']}: {e}")

conds_to_insert = [
    {
        "id": 9901,
        "name": "RSI >= 40 (No Sobrevendido)",
        "variable_id": 150,
        "operator": ">=",
        "value_type": "literal",
        "value_literal": "40",
        "enabled": True
    },
    {
        "id": 9902,
        "name": "Pullback a EMA20 (High >= EMA20)",
        "variable_id": 151,
        "operator": "==",
        "value_type": "literal",
        "value_literal": "True",
        "enabled": True
    },
    {
        "id": 9903,
        "name": "Tendencia Corta Bajista (EMA9 < EMA20)",
        "variable_id": 152,
        "operator": "==",
        "value_type": "literal",
        "value_literal": "True",
        "enabled": True
    }
]

for c in conds_to_insert:
    try:
        supabase.table('strategy_conditions').upsert(c).execute()
        print(f"Upserted cond {c['name']}")
    except Exception as e:
        print(f"Failed to upsert cond {c['name']}: {e}")
