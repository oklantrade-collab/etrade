import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def run_verify():
    print("--- VERIFICATION 1: SAR 15m in market_snapshot ---")
    res1 = sb.table('market_snapshot').select(
        'symbol, sar_15m, sar_trend_15m, sar_ini_high_15m, sar_ini_low_15m, sar_4h, sar_trend_4h, sar_phase, updated_at'
    ).neq('symbol', 'TEST').order('symbol').execute()
    for row in res1.data: print(row)

    print("\n--- VERIFICATION 2: PineScript signals in candles ---")
    res2 = sb.table('market_candles').select(
        'symbol, timeframe, open_time, close, pinescript_signal'
    ).eq('symbol', 'BTCUSDT').eq('timeframe', '15m').not_.is_('pinescript_signal', 'null').order('open_time', desc=True).limit(5).execute()
    if not res2.data:
        print("0 rows found. Signals will be saved in the next 15m cycle.")
    for row in res2.data: print(row)

    print("\n--- VERIFICATION 3: Hybrid cycle active ---")
    res3 = sb.table('pilot_diagnostics').select(
        'symbol, direction_evaluated, mtf_score_logged, cycle_type, timestamp'
    ).order('timestamp', desc=True).limit(12).execute()
    for row in res3.data: print(row)

    print("\n--- VERIFICATION 4: Cc Rules in DB ---")
    res4 = sb.table('trading_rules').select(
        'id, rule_code, name, direction, enabled, confidence'
    ).in_('rule_code', ['Cc11', 'Cc21']).order('rule_code').execute()
    for row in res4.data: print(row)

    print("\n--- VERIFICATION 5: Frankfurt active ---")
    try:
        res5 = sb.postgrest.rpc('exec_sql', {'sql_query': """
            SELECT symbol, cycle_type, 
                   COUNT(*) AS ciclos, 
                   MAX(timestamp) AS ultimo
            FROM pilot_diagnostics 
            WHERE timestamp >= NOW() - INTERVAL '20 minutes'
            GROUP BY symbol, cycle_type
            ORDER BY symbol, cycle_type;
        """}).execute()
        for row in res5.data: print(row)
    except:
        print("RPC exec_sql not available.")

if __name__ == "__main__":
    run_verify()
