import os
import dotenv
from binance.client import Client

root_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET') or os.getenv('BINANCE_API_SECRET')

client = Client(api_key, api_secret)
try:
    import time
    srv_time = client.futures_time()
    local_time = int(time.time() * 1000)
    client.TIME_OFFSET = int(srv_time['serverTime'] - local_time)
except Exception:
    pass

positions = client.futures_position_information(recvWindow=60000)
active = [p for p in positions if float(p.get('positionAmt', 0)) != 0]
print(f"Total active Binance Futures positions: {len(active)}")
for p in active:
    print(f"Symbol: {p['symbol']} | Side: {'LONG' if float(p['positionAmt']) > 0 else 'SHORT'} | Amount: {p['positionAmt']} | Entry: {p['entryPrice']} | Mark: {p['markPrice']} | PnL: {p['unRealizedProfit']}")
