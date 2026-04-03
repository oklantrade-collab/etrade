import os
from dotenv import load_dotenv
from supabase import create_client
import subprocess
import json

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

def run_query_1():
    print("\n--- QUERY 1 (pending_orders) ---")
    res = sb.table('pending_orders').select('symbol, direction, rule_code, limit_price, sl_price, tp1_price, band_name, basis_slope, status, created_at, expires_at').order('created_at', desc=True).limit(10).execute()
    if not res.data:
        print("No records found in pending_orders.")
    else:
        for r in res.data:
            print(r)

def run_query_2():
    print("\n--- QUERY 2 (pilot_diagnostics 20m) ---")
    # RPC or manual filter since we can't do GROUP BY easily with Postgrest Client without RPC
    # We fetch data and group in python for exact report
    res = sb.table('pilot_diagnostics').select('symbol, cycle_type, timestamp').gte('timestamp', 'now() - interval 20 minutes').execute()
    if not res.data:
        print("No records found in pilot_diagnostics (last 20m).")
    else:
        # Simple manual group by
        stats = {}
        for r in res.data:
            key = (r['symbol'], r['cycle_type'])
            if key not in stats: stats[key] = {'count': 0, 'last': r['timestamp']}
            stats[key]['count'] += 1
            if r['timestamp'] > stats[key]['last']: stats[key]['last'] = r['timestamp']
        for k, v in stats.items():
            print(f"Symbol: {k[0]}, Cycle: {k[1]}, Count: {v['count']}, Last: {v['last']}")

def run_query_3():
    print("\n--- QUERY 3 (system_logs swing) ---")
    # Filters: SWING, basis_not_flat, pending, Dd, LIMIT
    res = sb.table('system_logs').select('message, created_at').gte('created_at', 'now() - interval 1 hour').execute()
    if not res.data:
        print("No records found in system_logs (last 1h).")
    else:
        matches = [r for r in res.data if any(x in r['message'].upper() for x in ['SWING', 'BASIS_NOT_FLAT', 'PENDING', 'DD', 'LIMIT'])]
        sorted_m = sorted(matches, key=lambda x: x['created_at'], reverse=True)[:10]
        for m in sorted_m:
            print(m)

def run_query_4():
    print("\n--- QUERY 4 (market_snapshot basis) ---")
    res = sb.table('market_snapshot').select('symbol, price, basis, upper_6, lower_6, mtf_score, sar_phase, fibonacci_zone, updated_at').neq('symbol', 'TEST').order('symbol').execute()
    if not res.data:
        print("No records found in market_snapshot.")
    else:
        for r in res.data:
            print(r)

def run_query_5():
    print("\n--- QUERY 5 (Git status) ---")
    try:
        out1 = subprocess.check_output(['git', 'log', '--oneline', '-5'], stderr=subprocess.STDOUT).decode()
        print("Git log:\n", out1)
        out2 = subprocess.check_output(['git', 'ls-files', 'app/analysis/swing_detector.py'], stderr=subprocess.STDOUT).decode()
        print("ls-files detector:\n", out2 if out2 else "FILE NOT TRACKED\n")
        out3 = subprocess.check_output(['git', 'ls-files', 'app/strategy/swing_orders.py'], stderr=subprocess.STDOUT).decode()
        print("ls-files orders:\n", out3 if out3 else "FILE NOT TRACKED\n")
    except Exception as e:
        print(f"Git command failed: {e}")

if __name__ == "__main__":
    run_query_1()
    run_query_2()
    run_query_3()
    run_query_4()
    run_query_5()
