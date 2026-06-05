import os
import sys
from datetime import datetime, timezone

# Agregar backend al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    print("--- ULTIMOS 10 TRADES REGISTRADOS ---")
    res = sb.table('paper_trades') \
        .select('*') \
        .order('closed_at', desc=True) \
        .limit(10) \
        .execute()
    
    trades = res.data or []
    if not trades:
        print("No se encontraron trades.")
        return
        
    for t in trades:
        closed = t.get('closed_at') or t.get('created_at')
        print(f"ID: {t.get('id')} | Rule: {t.get('rule_code')} | Status: {t.get('status')} | "
              f"Closed At: {closed} | PNL USD: {t.get('total_pnl_usd')} | PNL %: {t.get('total_pnl_pct')}")

if __name__ == '__main__':
    main()
