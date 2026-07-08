import os
import sys
from datetime import datetime, timezone, date
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_growth():
    sb = get_supabase()
    today_str = date.today().isoformat() # 2026-07-01
    print(f"Checking stock growth for today: {today_str}")
    
    try:
        res = sb.table('technical_scores').select('*').execute()
        if not res.data:
            print("No technical scores found.")
            return
            
        today_scores = []
        for row in res.data:
            timestamp = row.get('timestamp', '')
            # Filter for today's scans only (2026-07-01)
            if timestamp.startswith(today_str):
                signals = row.get('signals_json') or {}
                change_pct = signals.get('change_pct') or 0.0
                price = signals.get('price') or 0.0
                today_scores.append({
                    'ticker': row['ticker'],
                    'price': price,
                    'change_pct': change_pct,
                    'rvol': row.get('rvol', 1.0),
                    'tech_score': row.get('technical_score', 0.0),
                    'apex_4h': row.get('apex_4h'),
                    'apex_1d': row.get('apex_1d'),
                    'apex_signal': row.get('apex_signal'),
                    'timestamp': timestamp,
                    'signals': signals
                })
        
        # Sort by change_pct descending
        today_scores.sort(key=lambda x: x['change_pct'], reverse=True)
        
        print(f"\nScanned Today ({len(today_scores)} tickers) sorted by Growth:")
        for idx, item in enumerate(today_scores, 1):
            signals = item['signals']
            last_scan_time = signals.get('last_scan_time', '--/--')
            print(f"#{idx:<2} | {item['ticker']:<5} | Price: ${item['price']:<6.2f} | Chg%: {item['change_pct']:+6.2f}% | RVol: {item['rvol']:<4.2f} | TechScore: {item['tech_score']:<4.1f} | Apex4H: {item['apex_4h']} | Apex1D: {item['apex_1d']} | Signal: {str(item['apex_signal']):<12} | Time: {last_scan_time} ({item['timestamp']})")

    except Exception as e:
        print(f"Error checking growth: {e}")

if __name__ == "__main__":
    check_growth()
