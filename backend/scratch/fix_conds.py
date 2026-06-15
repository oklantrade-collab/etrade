import os
import sys
import json
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv("c:/Fuentes/eTrade/backend/.env")

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(url, key)

conds_to_insert = [
    {
        "id": 9902,
        "name": "Pullback a EMA20 (High >= EMA20)",
        "variable_id": 151,
        "operator": "==",
        "value_type": "literal",
        "value_literal": "1",
        "enabled": True
    },
    {
        "id": 9903,
        "name": "Tendencia Corta Bajista (EMA9 < EMA20)",
        "variable_id": 152,
        "operator": "==",
        "value_type": "literal",
        "value_literal": "1",
        "enabled": True
    }
]

for c in conds_to_insert:
    try:
        supabase.table('strategy_conditions').upsert(c).execute()
        print(f"Upserted cond {c['name']}")
    except Exception as e:
        print(f"Failed to upsert cond {c['name']}: {e}")
