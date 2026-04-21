from app.core.supabase_client import get_supabase
import os

sb = get_supabase()
res = sb.table('trading_config').select('capital_forex_futures').eq('id', 1).execute()
print(f"Capital Forex Futures: {res.data}")

env_vars = ['CTRADER_CLIENT_ID', 'CTRADER_CLIENT_SECRET', 'CTRADER_ACCOUNT_ID', 'CTRADER_ACCESS_TOKEN']
for v in env_vars:
    val = os.getenv(v)
    print(f"{v}: {'EXISTS' if val else 'MISSING'}")
