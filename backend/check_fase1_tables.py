
from app.core.supabase_client import get_supabase
sb = get_supabase()

tables = ['strategy_variables', 'strategy_conditions', 'strategy_rules_v2', 'strategy_evaluations']
for t in tables:
    try:
        res = sb.table(t).select('*', count='exact').limit(1).execute()
        print(f"Table {t} EXISTS. Count: {res.count if hasattr(res, 'count') else 'N/A'}")
    except Exception as e:
        print(f"Table {t} MISSING: {e}")
