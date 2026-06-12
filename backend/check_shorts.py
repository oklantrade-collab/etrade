import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_shorts():
    sb = get_supabase()
    
    # Check all sides in positions table
    print("--- Checking sides in positions table ---")
    pos_res = sb.table("positions").select("side, status").execute()
    counts = {}
    for r in pos_res.data:
        side = str(r.get("side")).upper()
        status = str(r.get("status")).lower()
        key = (side, status)
        counts[key] = counts.get(key, 0) + 1
        
    for key, count in counts.items():
        print(f"Side: {key[0]} | Status: {key[1]} | Count: {count}")
        
    print("\n--- Recent 10 SHORT/sell positions (if any) ---")
    shorts = sb.table("positions").select("*").in_("side", ["SHORT", "short", "SELL", "sell"]).order("opened_at", desc=True).limit(10).execute()
    if not shorts.data:
        print("No SHORT/sell positions found in positions table.")
    for s in shorts.data:
        print(f"ID: {s['id']} | Symbol: {s['symbol']} | Side: {s['side']} | Rule: {s['rule_code']} | Status: {s['status']} | Opened: {s['opened_at']} | Closed: {s['closed_at']}")

if __name__ == "__main__":
    check_shorts()
