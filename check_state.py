import os
import sys
import pandas as pd
from app.core.supabase_client import get_supabase

def check_state():
    sb = get_supabase()
    
    # Check market snapshot for BTCUSDT
    print("--- MARKET SNAPSHOT ---")
    res = sb.table('market_snapshot').select('*').eq('symbol', 'BTCUSDT').execute()
    if res.data:
        snap = res.data[0]
        print(f"Symbol: {snap.get('symbol')}")
        print(f"Price: {snap.get('price')}")
        print(f"ADX: {snap.get('adx')}")
        print(f"MTF Score: {snap.get('mtf_score')}")
        print(f"SAR Trend: {snap.get('sar_trend')}")
        print(f"Regime Score (APEX): {snap.get('apex_regime_score')}")
    else:
        print("No snapshot found for BTCUSDT")

    # Check regime from system logs or market snapshot
    print("\n--- RECENT SYSTEM LOGS (Rule Matches) ---")
    res_logs = sb.table('system_logs').select('*').order('created_at', desc=True).limit(20).execute()
    if res_logs.data:
        for log in res_logs.data:
            if "Rule " in log.get('message', ''):
                print(f"{log['created_at']} | {log['message']} | Context: {log.get('context')}")

if __name__ == "__main__":
    check_state()
