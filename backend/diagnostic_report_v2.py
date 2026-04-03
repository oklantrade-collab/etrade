import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from supabase import create_client
import subprocess

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def run_query_1():
    print("\n--- QUERY 1 (pending_orders) ---")
    res = sb.table('pending_orders').select('*').order('created_at', desc=True).limit(10).execute()
    if not res.data: print("No records found in pending_orders.")
    else:
        for r in res.data:
            print(f"{r['symbol']} | {r['direction']} | {r['status']} | {r['limit_price']} | {r['created_at']}")

def run_query_2():
    print("\n--- QUERY 2 (pilot_diagnostics 20m) ---")
    limit_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    res = sb.table('pilot_diagnostics').select('symbol, cycle_type, timestamp').gte('timestamp', limit_time).execute()
    if not res.data: print("No records found in pilot_diagnostics (last 20m).")
    else:
        stats = {}
        for r in res.data:
            k = (r['symbol'], r['cycle_type'])
            if k not in stats: stats[k] = {'count': 0, 'last': r['timestamp']}
            stats[k]['count'] += 1
            if r['timestamp'] > stats[k]['last']: stats[k]['last'] = r['timestamp']
        for k, v in stats.items():
            print(f"Symbol: {k[0]:<10} | Cycle: {k[1]:<5} | Count: {v['count']:<3} | Last: {v['last']}")

def run_query_3():
    print("\n--- QUERY 3 (system_logs 1h) ---")
    limit_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    res = sb.table('system_logs').select('message, created_at').gte('created_at', limit_time).execute()
    if not res.data: print("No records found in system_logs.")
    else:
        keywords = ['SWING', 'BASIS', 'PENDING', 'DD', 'LIMIT']
        matches = [r for r in res.data if any(k in r['message'].upper() for k in keywords)]
        for m in sorted(matches, key=lambda x: x['created_at'], reverse=True)[:10]:
            print(f"{m['created_at'][:19]} | {m['message']}")

def run_query_4():
    print("\n--- QUERY 4 (market_snapshot) ---")
    res = sb.table('market_snapshot').select('symbol, price, basis, upper_6, lower_6, mtf_score, sar_phase, updated_at').neq('symbol', 'TEST').order('symbol').execute()
    if not res.data: print("No records.")
    else:
        for r in res.data:
            print(f"{r['symbol']:<10} | Price: {r['price']:<10} | Basis: {r['basis']:<10} | SAR: {r['sar_phase']:<8} | MTF: {r['mtf_score']:<6} | Updated: {r['updated_at']}")

def run_query_5():
    print("\n--- QUERY 5 (Git files) ---")
    try:
        log = subprocess.check_output(['git', 'log', '--oneline', '-5']).decode()
        print(f"Git log:\n{log}")
        for f in ['app/analysis/swing_detector.py', 'app/strategy/swing_orders.py']:
            out = subprocess.check_output(['git', 'ls-files', f]).decode().strip()
            print(f"Tracking {f}: {'YES' if out else 'NO (NOT TRACKED)'}")
    except: print("Git error.")

if __name__ == "__main__":
    run_query_1()
    run_query_2()
    run_query_3()
    run_query_4()
    run_query_5()
