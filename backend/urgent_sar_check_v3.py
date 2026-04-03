import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def run_urgent_checks():
    print("--- URGENTE 1: Estado BTC vs SAR ---")
    p1 = sb.table('positions').select('*').eq('symbol', 'BTCUSDT').execute()
    m1 = sb.table('market_snapshot').select('sar_trend_4h, sar_phase').eq('symbol', 'BTCUSDT').single().execute()
    
    if p1.data:
        p = p1.data[-1] # Ultima en la lista (generalmente abierta si hay o ultima cerrada)
        m = m1.data if m1.data else {}
        print(f"BTC Position Status: {p['status']} | Reason: {p.get('close_reason')} | Closed At: {p.get('closed_at')}")
        print(f"BTC SAR 4h Trend: {m.get('sar_trend_4h')} | Phase: {m.get('sar_phase')}")

    print("\n--- URGENTE 2: P&L si sigue abierta ---")
    p2 = sb.table('positions').select('*').eq('symbol', 'BTCUSDT').eq('status', 'open').execute()
    m2 = sb.table('market_snapshot').select('price').eq('symbol', 'BTCUSDT').single().execute()
    
    if p2.data:
        p = p2.data[0]
        price = m2.data.get('price', 0) if m2.data else 0
        entry = float(p.get('avg_entry_price') or p.get('entry_price') or 0)
        pnl = round((price - entry) / entry * 100, 2) if entry > 0 else 0
        print(f"BTC is OPEN at {entry} | Current Price: {price} | P&L: {pnl}%")
    else:
        print("BTC is already CLOSED (or no open position found).")

    print("\n--- VERIFICACIÓN 3: Evaluación SHORT ---")
    res3 = sb.table('pilot_diagnostics').select('*').eq('cycle_type', '15m').order('timestamp', desc=True).limit(8).execute()
    if res3.data:
        for row in res3.data:
            print(f"{row['symbol']} | Evaluation: {row['direction_evaluated']} | Rule: {row.get('rule_evaluated')} | MTF: {row.get('mtf_score_logged')} | {row['timestamp']}")

if __name__ == "__main__":
    run_urgent_checks()
