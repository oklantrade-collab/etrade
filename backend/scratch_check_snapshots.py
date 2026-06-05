import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_snapshots():
    sb = get_supabase()
    res = sb.table('market_snapshot').select('*').execute()
    print("=== All Market Snapshots ===")
    if res.data:
        for snap in res.data:
            print(f"Symbol: {snap.get('symbol')} | Price: {snap.get('price')} | Updated At: {snap.get('updated_at')}")
    else:
        print("No snapshots found")

if __name__ == "__main__":
    check_snapshots()
