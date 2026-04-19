import sys
import os
sys.path.append(os.path.abspath('.'))

from app.core.supabase_client import get_supabase
from datetime import date

def run_diagnostic():
    sb = get_supabase()
    today = date.today().isoformat()
    
    query = """
    SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN market_cap_mln > 10000 THEN 1 END) as cap_over_10b,
        COUNT(CASE WHEN rs_score_6m > 85 THEN 1 END) as rs_over_85,
        COUNT(CASE WHEN inst_ownership_pct > 50 THEN 1 END) as inst_over_50,
        COUNT(CASE WHEN revenue_growth_yoy > 15 THEN 1 END) as rev_over_15,
        COUNT(CASE WHEN gross_margin > 35 THEN 1 END) as margin_over_35
    FROM watchlist_daily 
    WHERE date = '{today}';
    """.replace("{today}", today)
    
    try:
        # Intentamos vía exec_sql si existe, si no fetch y procesamos local
        res = sb.rpc('exec_sql', {'sql_query': query}).execute()
        print(f"Diagnóstico SQL: {res.data}")
    except:
        # Fallback: Procesamiento local para el diagnóstico
        res = sb.table('watchlist_daily').select('*').eq('date', today).execute()
        data = res.data
        total = len(data)
        metrics = {
            "total": total,
            "cap_over_10b": sum(1 for r in data if (r.get('market_cap_mln') or 0) > 10000),
            "rs_over_85": sum(1 for r in data if (r.get('rs_score_6m') or 0) > 85),
            "inst_over_50": sum(1 for r in data if (r.get('inst_ownership_pct') or 0) > 50),
            "rev_over_15": sum(1 for r in data if (r.get('revenue_growth_yoy') or 0) > 15),
            "margin_over_35": sum(1 for r in data if (r.get('gross_margin') or 0) > 35)
        }
        print(f"Diagnóstico [Local]: {metrics}")

if __name__ == "__main__":
    run_diagnostic()
