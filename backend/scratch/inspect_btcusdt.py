import os
import sys

# Add backend directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.core.supabase_client import get_supabase

def inspect():
    sb = get_supabase()
    pos_id = "bc22cce1-658d-46ea-841d-de70c705b852"
    
    # 1. Fetch exact position
    print("=== EXACT POSITION DATA ===")
    res = sb.table('positions').select('*').eq('id', pos_id).execute()
    if res.data:
        pos = res.data[0]
        for k, v in pos.items():
            print(f"{k}: {v}")
    else:
        print("Position not found!")

    # 2. Fetch system logs specifically referencing the position ID or BTCUSDT
    # during its lifetime (2026-06-01 00:20:00 to 2026-06-01 01:25:00 UTC)
    print("\n=== SYSTEM LOGS DURING LIFETIME ===")
    res_logs = sb.table('system_logs').select('*')\
        .gte('created_at', '2026-06-01T00:15:00')\
        .lte('created_at', '2026-06-01T01:25:00')\
        .execute()
    
    logs = res_logs.data or []
    # Sort logs by created_at
    logs = sorted(logs, key=lambda x: x['created_at'])
    
    for log in logs:
        msg = log.get('message', '')
        ctx = str(log.get('context') or '')
        if pos_id in msg or pos_id in ctx or 'BTCUSDT' in msg or 'BTCUSDT' in ctx:
            print(f"{log['created_at']} | {log['level']} | {msg} | Context: {log.get('context')}")

if __name__ == "__main__":
    inspect()
