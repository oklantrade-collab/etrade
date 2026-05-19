import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

from app.core.position_sizing import calculate_position_size

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("=== RUNNING SIZE CALCULATION FOR BTCUSDT ===")
sizing = calculate_position_size(
    symbol='BTCUSDT',
    entry_price=78078.2,
    sl_price=81682.067,
    market_type='crypto_futures',
    trade_number=1,
    regime='riesgo_medio',
    supabase=sb
)

print("Result:")
for k, v in sizing.items():
    print(f"  {k}: {v}")
