import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_system_config, get_supabase
from app.core.config import DEFAULT_CONFIG
sb = get_supabase()

config = get_system_config()
allowed = config.get("allowed_symbols", DEFAULT_CONFIG.get("allowed_symbols", []))

if isinstance(allowed, str):
    allowed = [s.strip() for s in allowed.split(",")]

# Convert to internal format for DB operations
def to_internal(sym):
    if sym.endswith("USDT"): return sym[:-4] + "/USDT"
    return sym
allowed_internal = [to_internal(s) for s in allowed]

print(f"Keeping only: {allowed_internal}")

# Get all unique symbols in DB
res = sb.table("market_candles").select("symbol").execute()
db_symbols = list(set([r["symbol"] for r in res.data]))
print(f"Found symbols in DB: {db_symbols}")

for sym in db_symbols:
    if sym not in allowed_internal:
        print(f"Deleting {sym}...")
        sb.table("market_candles").delete().eq("symbol", sym).execute()
        sb.table("technical_indicators").delete().eq("symbol", sym).execute()
        sb.table("volume_spikes").delete().eq("symbol", sym).execute()
        sb.table("trading_signals").delete().eq("symbol", sym).execute()
        
print("Cleanup done!")
