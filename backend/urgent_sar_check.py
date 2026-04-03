import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def run_urgent_checks():
    print("--- URGENTE 1: Estado BTC vs SAR ---")
    res1 = sb.rpc('exec_sql', {'sql_query': """
        SELECT p.symbol, p.status, 
               p.close_reason, p.closed_at,
               ms.sar_trend_4h, ms.sar_phase
        FROM positions p
        JOIN market_snapshot ms ON p.symbol = ms.symbol
        WHERE p.symbol = 'BTCUSDT'
        ORDER BY p.updated_at DESC
        LIMIT 1;
    """}).execute()
    if res1.data:
        for row in res1.data: print(row)
    else:
        # Fallback if exec_sql fails or join is empty
        p = sb.table('positions').select('*').eq('symbol', 'BTCUSDT').order('updated_at', desc=True).limit(1).execute()
        m = sb.table('market_snapshot').select('sar_trend_4h, sar_phase').eq('symbol', 'BTCUSDT').single().execute()
        print("Position:", p.data[0] if p.data else "None")
        print("Snapshot:", m.data if m.data else "None")

    print("\n--- URGENTE 2: P&L si sigue abierta ---")
    res2 = sb.rpc('exec_sql', {'sql_query': """
        SELECT p.symbol, p.avg_entry_price, 
               ms.price,
               ROUND((ms.price - p.avg_entry_price) / p.avg_entry_price * 100, 2) AS pnl_pct
        FROM positions p
        JOIN market_snapshot ms ON p.symbol = ms.symbol
        WHERE p.symbol = 'BTCUSDT' AND p.status = 'open';
    """}).execute()
    for row in res2.data: print(row)

    print("\n--- VERIFICACIÓN 3: Evaluación SHORT ---")
    res3 = sb.table('pilot_diagnostics').select(
        'symbol, direction_evaluated, rule_evaluated, rule_triggered, mtf_score_logged, timestamp'
    ).eq('cycle_type', '15m').order('timestamp', desc=True).limit(8).execute()
    for row in res3.data: print(row)

if __name__ == "__main__":
    run_urgent_checks()
