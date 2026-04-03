
import pandas as pd
from app.core.supabase_client import get_supabase
sb = get_supabase()

tables = ['strategy_variables', 'strategy_conditions', 'strategy_rules_v2']
expected = {'strategy_variables': 46, 'strategy_conditions': 45, 'strategy_rules_v2': 14}

print("VERIFICACIÓN Fase 1 - Strategy Engine v1.0")
print("-" * 50)
print(f"{'TABLA':<25} | {'REGISTROS':<10}")
print("-" * 50)

for t in tables:
    try:
        res = sb.table(t).select('*', count='exact').limit(1).execute()
        count = res.count if hasattr(res, 'count') else 0
        print(f"{t:<25} | {count:<10}")
    except Exception as e:
        print(f"{t:<25} | ERROR (MISSING)")

print("-" * 50)
