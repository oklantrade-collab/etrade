import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv("c:/Fuentes/eTrade/backend/.env")

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(url, key)

new_conditions = [
    {
        "id": 9901,
        "name": "RSI >= 40 (No Sobrevendido)",
        "variable": {"source_field": "rsi_14"},
        "operator": ">=",
        "value_literal": "40"
    },
    {
        "id": 9902,
        "name": "Pullback a EMA20 (High >= EMA20)",
        "variable": {"source_field": "high_touched_ema20"},
        "operator": "==",
        "value_literal": "True"
    },
    {
        "id": 9903,
        "name": "Tendencia Corta (EMA9 < EMA20)",
        "variable": {"source_field": "ema9_below_ema20"},
        "operator": "==",
        "value_literal": "True"
    }
]

for cond in new_conditions:
    try:
        res = supabase.table('strategy_conditions').upsert(cond).execute()
        print(f"Upserted {cond['name']}")
    except Exception as e:
        print(f"Failed to upsert {cond['name']}: {e}")

