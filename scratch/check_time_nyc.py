import sys, os
from datetime import datetime, timezone, timedelta
sys.path.insert(0, r"c:\Fuentes\eTrade\backend")
from app.core.market_hours import get_nyc_now, is_market_open

nyc_now = get_nyc_now()
is_open, status = is_market_open()

print(f"Local time (Lima?): {datetime.now()}")
print(f"UTC time: {datetime.now(timezone.utc)}")
print(f"NYC time: {nyc_now}")
print(f"Market status: {status} (is_open={is_open})")
