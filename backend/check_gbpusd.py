import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_market_data():
    sb = get_supabase()
    print("--- GBPUSD MARKET DATA AROUND 15:15 UTC ---")
    data = sb.table('forex_market_data').select('*').eq('symbol', 'GBPUSD').gte('updated_at', '2026-06-01T15:00:00').lte('updated_at', '2026-06-01T15:30:00').order('updated_at', desc=False).execute()
    for d in data.data:
        try:
            print(f"[{d.get('updated_at')}] Price: {d.get('price')} ADX: {d.get('adx')} MTF: {d.get('mtf_score')} SAR4H: {d.get('sar_trend_4h')} SAR15m: {d.get('sar_trend_15m')} Regime: {d.get('regime')}")
            print(f"    EMA3: {d.get('ema_3')} EMA9: {d.get('ema_9')} EMA20: {d.get('ema_20')}")
        except Exception as e:
            pass

if __name__ == "__main__":
    check_market_data()
