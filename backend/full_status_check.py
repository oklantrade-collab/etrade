import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def run_checks():
    print("--- QUERY 1: Trades del día ---")
    # Using a simple query for the most recent 10 trades as a proxy for "today's trades"
    res1 = sb.table('positions').select('*').order('opened_at', desc=True).limit(10).execute()
    for row in res1.data:
        print(f"{row['symbol']} | {row['side']} | {row['status']} | P&L USD: {row.get('pnl_usd')} | {row.get('closed_at')}")

    print("\n--- QUERY 2: Posiciones abiertas ---")
    res2 = sb.table('positions').select('symbol, status, side, avg_entry_price, opened_at').eq('status', 'open').execute()
    if not res2.data:
        print("0 filas (sistema limpio)")
    else:
        for row in res2.data: print(row)

    print("\n--- QUERY 3: Pilot diagnostics (últimos 20 min) ---")
    res3 = sb.table('pilot_diagnostics').select(
        'symbol, direction_evaluated, rule_evaluated, rule_triggered, mtf_score_logged, timestamp'
    ).eq('cycle_type', '15m').order('timestamp', desc=True).limit(10).execute()
    for row in res3.data:
        print(f"{row['symbol']} | Dir: {row['direction_evaluated']} | Rule: {row.get('rule_evaluated')} | Triggered: {row['rule_triggered']} | MTF: {row.get('mtf_score_logged')} | {row['timestamp']}")

    print("\n--- QUERY 4: Estado Snapshot (Short readiness) ---")
    res4 = sb.table('market_snapshot').select(
        'symbol, pinescript_signal, sar_trend_15m, sar_trend_4h, mtf_score'
    ).neq('symbol', 'TEST').order('symbol').execute()
    for row in res4.data: print(row)

if __name__ == "__main__":
    run_checks()
