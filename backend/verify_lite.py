import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def run_verify():
    print("V1")
    r1 = sb.table('market_snapshot').select('symbol,sar_15m,sar_trend_15m,updated_at').neq('symbol','TEST').execute()
    for row in r1.data: print(row)
    
    print("\nV2")
    r2 = sb.table('market_candles').select('symbol,open_time,pinescript_signal').eq('symbol','BTCUSDT').eq('timeframe','15m').not_.is_('pinescript_signal','null').order('open_time',desc=True).limit(3).execute()
    for row in r2.data: print(row)

    print("\nV3")
    r3 = sb.table('pilot_diagnostics').select('symbol,cycle_type,timestamp').order('timestamp',desc=True).limit(8).execute()
    for row in r3.data: print(row)

run_verify()
