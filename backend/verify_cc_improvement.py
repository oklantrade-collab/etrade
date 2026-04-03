import os
from supabase import create_client
from dotenv import load_dotenv
import json

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

print("--- CHECK 3: Reglas Cc en DB ---")
res = sb.table('trading_rules').select('rule_code, name, direction, enabled').in_('rule_code', ['Cc11', 'Cc21']).execute()
for row in res.data:
    print(row)

print("\n--- CHECK 2: Señales B/S en market_candles ---")
res = sb.table('market_candles')\
    .select('open_time, close, pinescript_signal')\
    .eq('symbol', 'BTCUSDT')\
    .eq('timeframe', '15m')\
    .not_.is_('pinescript_signal', 'null')\
    .order('open_time', desc=True)\
    .limit(5)\
    .execute()

if not res.data:
    print("0 filas encontradas. Las señales se guardarán en el próximo ciclo de 15m.")
else:
    for row in res.data:
        print(row)
