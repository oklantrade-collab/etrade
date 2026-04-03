import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
supabase = create_client(url, key)

def print_query(name, data):
    print(f"\n{'='*50}\n{name}\n{'='*50}")
    if not data:
        print("No results found.")
    elif isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], dict):
            keys = list(data[0].keys())
            print(" | ".join(keys))
            print("-" * (len(keys) * 15))
            for row in data:
                values = [str(row.get(k, 'None')) for k in keys]
                print(" | ".join(values))
        else:
            print(data)
    else:
        print(data)

# QUERY 1 — Snapshot logs in Frankfurt
try:
    res1 = supabase.table('system_logs').select('message, created_at').eq('module', 'SNAPSHOT').order('created_at', desc=True).limit(20).execute()
    print_query("QUERY 1 — Frankfurt Snapshot Logs", res1.data)
except Exception as e:
    print(f"Error QUERY 1: {e}")

# QUERY 2 — Market Snapshot (MTF and updated_at)
try:
    res2 = supabase.table('market_snapshot').select('symbol, mtf_score, regime, updated_at').neq('symbol', 'TEST').order('symbol').execute()
    print_query("QUERY 2 — Market Snapshot Post-Cycle", res2.data)
except Exception as e:
    print(f"Error QUERY 2: {e}")

# QUERY 3 — Frankfurt 21:00 cycle check (using pilot_diagnostics)
# Using table select and group in python since RPC might fail
try:
    # Get last 20 mins of diagnostics
    res3 = supabase.table('pilot_diagnostics')\
        .select('symbol, cycle_type, timestamp')\
        .gte('timestamp', (datetime.now(timezone.utc)).isoformat().replace('+00:00', ''))\
        .execute()
    # Actually simpler to just count from the raw data
    raw_diag = res3.data or []
    summary = {}
    for d in raw_diag:
        key = (d['symbol'], d['cycle_type'])
        if key not in summary:
            summary[key] = {'ciclos': 0, 'ultimo': d['timestamp']}
        summary[key]['ciclos'] += 1
        if d['timestamp'] > summary[key]['ultimo']:
            summary[key]['ultimo'] = d['timestamp']
    
    rows = [{'symbol': k[0], 'cycle_type': k[1], 'ciclos': v['ciclos'], 'ultimo': v['ultimo']} for k, v in summary.items()]
    rows.sort(key=lambda x: (x['symbol'], x['cycle_type']))
    print_query("QUERY 3 — Frankfurt 21:00 Cycle Diagnostics", rows)
except Exception as e:
     # If timestamp comparison fails, just get the count
    print(f"Error QUERY 3 with filter: {e}")
    res3_alt = supabase.table('pilot_diagnostics')\
        .select('symbol, cycle_type, timestamp')\
        .order('timestamp', desc=True)\
        .limit(20)\
        .execute()
    print_query("QUERY 3 Alt — Recent Diagnostics", res3_alt.data)

# QUERY 4 — Parameter Thresholds
try:
    res4 = supabase.table('parameter_bounds').select('parameter_name, current_value, min_value').ilike('parameter_name', 'mtf_threshold%').order('parameter_name').execute()
    print_query("QUERY 4 — MTF Threshold Bounds", res4.data)
except Exception as e:
    print(f"Error QUERY 4: {e}")

# QUERY 5 / ACCIÓN 1 — Smart Exit parameters
try:
    res5 = supabase.table('trading_config').select('exit_on_signal_reversal, exit_mtf_threshold, min_profit_exit_pct, min_profit_exit_usd').eq('id', 1).execute()
    print_query("QUERY 5 / ACCIÓN 1 — Smart Exit Config", res5.data)
except Exception as e:
    print(f"Error QUERY 5: {e}")
