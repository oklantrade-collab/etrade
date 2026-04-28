from app.core.market_hours import get_market_status_dict, get_nyc_now, is_market_open
import datetime

print(f"Current UTC: {datetime.datetime.now(datetime.timezone.utc)}")
print(f"NYC Now: {get_nyc_now()}")
print(f"Is Market Open: {is_market_open()}")
print(f"Market Status Dict: {get_market_status_dict()}")
