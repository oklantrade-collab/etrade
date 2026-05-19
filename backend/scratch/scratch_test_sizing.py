import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

from app.core.position_sizing import calculate_position_size

print("=== TESTING POSITION SIZING ===")
try:
    res = calculate_position_size(
        symbol="BTCUSDT",
        entry_price=78244.7,
        sl_price=78205.5,
        market_type="crypto_futures",
        trade_number=1,
        regime="riesgo_medio",
        supabase=sb
    )
    print("Sizing Result:")
    for k, v in res.items():
        print(f"  {k}: {v}")
except Exception as e:
    import traceback
    print("Sizing Failed!")
    traceback.print_exc()
