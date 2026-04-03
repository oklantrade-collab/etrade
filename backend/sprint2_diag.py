"""Deep diagnostic: why are only stablecoins in technical_indicators and 0 volume_spikes?"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

sb = get_supabase()

# 1. Total technical_indicators count
res = sb.table("technical_indicators").select("id", count="exact").execute()
print(f"Total technical_indicators rows: {res.count}")

# 2. Distinct symbols in technical_indicators
res2 = sb.table("technical_indicators").select("symbol").execute()
syms = set(r["symbol"] for r in res2.data)
print(f"Distinct symbols in technical_indicators: {len(syms)}")
for s in sorted(syms):
    print(f"  - {s}")

# 3. Check system_logs for errors related to indicators or spikes
print("\n--- ERRORS in system_logs (last 20) ---")
logs = sb.table("system_logs").select("module, level, message, created_at").eq("level", "ERROR").order("created_at", desc=True).limit(20).execute()
for l in logs.data:
    print(f"  [{l['created_at']}] [{l['module']}] {l['message'][:120]}")

# 4. WARNINGS related to insufficient data
print("\n--- WARNINGS containing 'Insufficient' (last 20) ---")
wlogs = sb.table("system_logs").select("module, message, created_at").eq("level", "WARNING").like("message", "%Insufficient%").order("created_at", desc=True).limit(20).execute()
for l in wlogs.data:
    print(f"  [{l['created_at']}] {l['message'][:120]}")

# 5. Check the EXCLUDED_SYMBOLS config
print("\n--- system_config: excluded_symbols ---")
cfg = sb.table("system_config").select("key, value").eq("key", "excluded_symbols").execute()
if cfg.data:
    print(f"  {cfg.data[0]['value']}")
else:
    print("  NOT SET")

# 6. Check last logs for spike detection
print("\n--- Logs containing 'spike' (last 15) ---")
slogs = sb.table("system_logs").select("module, level, message, created_at").ilike("message", "%spike%").order("created_at", desc=True).limit(15).execute()
for l in slogs.data:
    print(f"  [{l['level']}] [{l['created_at']}] {l['message'][:140]}")

# 7. Count market_candles per symbol to check fetch worked
print("\n--- market_candles count per symbol (top 10 by count) ---")
candles = sb.table("market_candles").select("symbol").execute()
from collections import Counter
ctr = Counter(r["symbol"] for r in candles.data)
for sym, cnt in ctr.most_common(10):
    print(f"  {sym}: {cnt} candles")
