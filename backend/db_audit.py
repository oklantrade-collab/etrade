
import os
import sys
from datetime import datetime, timezone
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_table_counts():
    sb = get_supabase()
    tables = [
        "market_candles", "system_logs", "technical_scores", 
        "market_data_5m", "trading_signals", "strategy_evaluations",
        "trade_opportunities", "trades_active", "trades_journal"
    ]
    
    print(f"--- DATABASE HEALTH CHECK {datetime.now(timezone.utc).isoformat()} ---")
    
    reports = []
    for table in tables:
        try:
            res = sb.table(table).select("id", count="exact").limit(1).execute()
            count = res.count or 0
            reports.append({"table": table, "count": count})
        except Exception as e:
            reports.append({"table": table, "count": "Error/Not found"})
    
    # Sort by count
    reports.sort(key=lambda x: x["count"] if isinstance(x["count"], int) else 0, reverse=True)
    
    for r in reports:
        print(f"- {r['table']}: {r['count']} rows")

if __name__ == "__main__":
    check_table_counts()
