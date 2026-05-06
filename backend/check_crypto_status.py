import os
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Ensure we can import from app
import sys
sys.path.insert(0, 'c:/Fuentes/eTrade/backend')

from app.core.supabase_client import get_supabase

def check_crypto_status():
    load_dotenv('c:/Fuentes/eTrade/backend/.env')
    sb = get_supabase()
    
    print("--- Market Snapshot Status ---")
    snaps = sb.table('market_snapshot').select('*').limit(5).execute()
    if snaps.data:
        for s in snaps.data:
            print(f"Symbol: {s.get('symbol')}, Price: {s.get('price')}, Updated At: {s.get('updated_at') or s.get('timestamp')}")
    else:
        print("No data in market_snapshot")
        
    print("\n--- Last Cron Cycles ---")
    cycles = sb.table('cron_cycles').select('*').order('started_at', desc=True).limit(5).execute()
    if cycles.data:
        for c in cycles.data:
            print(f"ID: {c['id']}, Started: {c['started_at']}, Status: {c['status']}, Errors: {c['errors']}")
    else:
        print("No data in cron_cycles")
        
    print("\n--- Last Error Logs ---")
    logs = sb.table('system_logs').select('*').eq('level', 'ERROR').order('created_at', desc=True).limit(5).execute()
    if logs.data:
        for l in logs.data:
            print(f"Module: {l['module']}, Message: {l['message']}, Context: {l['context']}")
    else:
        print("No ERROR logs found")

    print("\n--- Positions Count ---")
    pos = sb.table('positions').select('id', count='exact').eq('status', 'open').execute()
    print(f"Open Positions: {pos.count if hasattr(pos, 'count') else len(pos.data)}")

if __name__ == "__main__":
    check_crypto_status()
