"""Run Sprint 3 SQL migration via Supabase REST API."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.core.supabase_client import get_supabase

sb = get_supabase()

# The SQL needs to be run in Supabase SQL Editor.
# Let's verify what tables/columns already exist.

print("=== Checking existing tables ===")

# Check trading_signals columns
try:
    r = sb.table("trading_signals").select("*").limit(1).execute()
    if r.data:
        print(f"trading_signals columns: {list(r.data[0].keys())}")
    else:
        print("trading_signals: table exists but empty")
except Exception as e:
    print(f"trading_signals: {e}")

# Check news_sentiment
try:
    r = sb.table("news_sentiment").select("*").limit(1).execute()
    print(f"news_sentiment: table exists, {len(r.data)} rows")
except Exception as e:
    print(f"news_sentiment: {e}")

# Check candle_patterns
try:
    r = sb.table("candle_patterns").select("*").limit(1).execute()
    print(f"candle_patterns: table exists, {len(r.data)} rows")
except Exception as e:
    print(f"candle_patterns: {e}")

# Check volume_spikes
try:
    r = sb.table("volume_spikes").select("*").limit(1).execute()
    if r.data:
        print(f"volume_spikes columns: {list(r.data[0].keys())}")
    else:
        print("volume_spikes: table exists but empty")
except Exception as e:
    print(f"volume_spikes: {e}")

# Check cron_cycles
try:
    r = sb.table("cron_cycles").select("*").limit(1).execute()
    if r.data:
        print(f"cron_cycles columns: {list(r.data[0].keys())}")
    else:
        print("cron_cycles: table exists but empty")
except Exception as e:
    print(f"cron_cycles: {e}")

print("\n=== Done ===")
print("If news_sentiment or candle_patterns tables don't exist,")
print("please run migration_003_sprint3.sql in the Supabase SQL Editor.")
