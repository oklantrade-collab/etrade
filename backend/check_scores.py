import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_scores():
    sb = get_supabase()
    
    print("=== TECHNICAL SCORES ===")
    try:
        res = sb.table('technical_scores').select('*').execute()
        if res.data:
            for row in res.data:
                signals = row.get('signals_json') or {}
                last_scan = row.get('timestamp', '--/--')
                rvol = row.get('rvol')
                rvol_str = f"{rvol:.2f}" if rvol is not None else "None"
                change_pct = signals.get('change_pct')
                change_pct_str = f"{change_pct:+.2f}%" if change_pct is not None else "None"
                price = signals.get('price')
                price_str = f"${price:.2f}" if price is not None else "None"
                apex_4h = row.get('apex_4h')
                apex_1d = row.get('apex_1d')
                apex_signal = row.get('apex_signal')
                
                print(f"Ticker: {row['ticker']:<5} | Price: {price_str:<7} | Chg%: {change_pct_str:<7} | RVol: {rvol_str:<6} | TechScore: {row['technical_score']:<4} | Apex4H: {apex_4h} | Apex1D: {apex_1d} | Signal: {str(apex_signal):<10} | Updated: {last_scan}")
        else:
            print("No records in technical_scores.")
    except Exception as e:
        print(f"Error reading technical_scores: {e}")

    print("\n=== MARKET SNAPSHOT ===")
    try:
        res_snap = sb.table('market_snapshot').select('*').execute()
        if res_snap.data:
            for row in res_snap.data:
                print(f"Symbol: {row['symbol']:<5} | Price: ${row['price']:<6.2f} | FibZone: {row.get('fibonacci_zone')} | Apex4H: {row.get('apex_4h')} | Apex1D: {row.get('apex_1d')} | Signal: {row.get('apex_signal')} | Updated: {row.get('updated_at')}")
        else:
            print("No records in market_snapshot.")
    except Exception as e:
        print(f"Error reading market_snapshot: {e}")

if __name__ == "__main__":
    check_scores()
