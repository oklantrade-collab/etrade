import os
from dotenv import load_dotenv
from supabase import create_client
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.getcwd(), '..'))
from app.core.position_sizing import calculate_position_size

load_dotenv('.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

print("CHECK 1 — Simulacion de Sizing (BTC)")
print("-" * 50)
res = calculate_position_size(
    symbol="BTCUSDT",
    entry_price=70934.0,
    sl_price=70154.0, # ~1.1% distance
    market_type="crypto_futures",
    trade_number=1,
    regime="riesgo_medio",
    supabase=sb
)
if res:
    print(f"Capital Base: ${res['capital_base']}")
    print(f"Leverage:     {res['leverage']}x")
    print(f"USD Amount:   ${res['usd_amount']}")
    print(f"Nocional:     ${res['nocional']}")
    print(f"Qty:          {res['quantity']} BTC")
    print(f"Riesgo USD:   ${res['risk_usd']} (1%)")

print("\nCHECK 2 — Posiciones actuales corregidas")
print("-" * 50)
pos_res = sb.table('positions').select('symbol, size, avg_entry_price').eq('status', 'open').execute()
for p in pos_res.data:
    val_usd = float(p['size']) * float(p['avg_entry_price'] or 0)
    print(f"{p['symbol']:9} | Size: {p['size']:>9} | Valor: ${val_usd:>8.2f}")
