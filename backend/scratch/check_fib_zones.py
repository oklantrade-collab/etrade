import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table("technical_scores").select("ticker, signals_json").limit(2).execute()
for r in (res.data or []):
    sj = r.get("signals_json") or {}
    fz15 = sj.get("fib_zone_15m", "N/A")
    fz1d = sj.get("fib_zone_1d", "N/A")
    mvmt = sj.get("movement_15m", "N/A")
    print(f"{r['ticker']:8s} fib_zone_15m={fz15}  fib_zone_1d={fz1d}  movement={mvmt}")
