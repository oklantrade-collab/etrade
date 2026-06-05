import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_snap():
    sb = get_supabase()
    res = sb.table('market_snapshot').select('*').eq('symbol', 'GBPUSD').execute()
    print("=== GBPUSD Snapshot ===")
    if res.data:
        snap = res.data[0]
        for k, v in snap.items():
            print(f"{k}: {v}")
    else:
        print("No snapshot found for GBPUSD")

if __name__ == "__main__":
    check_snap()
