import os
import sys
from pprint import pprint
# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

from app.core.supabase_client import get_supabase

def query_status():
    sb = get_supabase()
    
    print("--- RECENT HALCON SCORES ---")
    res_scores = sb.table('halcon_scores_log').select('*').order('created_at', desc=True).limit(2).execute()
    for s in res_scores.data:
        print(f"Time: {s['created_at']}, Symbol: {s['symbol']}, Score: {s['score_final']}, Semaforo: {s['semaforo']}, Reason: {s['reason']}")
        
    print("\n--- RECENT CENTINELA DECISIONS ---")
    res_dec = sb.table('centinela_decisions_log').select('*').order('created_at', desc=True).limit(2).execute()
    for d in res_dec.data:
        print(f"Time: {d['created_at']}, Symbol: {d['symbol']}, Position ID: {d['position_id']}, Decision: {d['decision']}, Reason: {d['reason']}")

    print("\n--- CURRENT OPEN POSITIONS (Supabase sync) ---")
    res_pos = sb.table('forex_positions').select('*').eq('status', 'OPEN').execute()
    if res_pos.data:
        for p in res_pos.data:
            print(f"FOREX - ID: {p['id']}, Symbol: {p['symbol']}, Volume: {p['volume']}, PnL: {p.get('unrealized_pnl', 0)}")
    else:
        print("No open positions found in forex_positions.")
        
    res_crypt = sb.table('crypto_positions').select('*').eq('status', 'OPEN').execute()
    if res_crypt.data:
        for p in res_crypt.data:
            print(f"CRYPTO - ID: {p['id']}, Symbol: {p['symbol']}, Volume: {p['volume']}, PnL: {p.get('unrealized_pnl', 0)}")
    else:
        print("No open positions found in crypto_positions.")

if __name__ == '__main__':
    query_status()
