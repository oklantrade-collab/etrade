import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase

def check_crypto():
    sb = get_supabase()
    
    print("--- 1. Recent Positions (All Statuses) ---")
    pos = sb.table("positions").select("*").order("opened_at", desc=True).limit(10).execute()
    for p in pos.data:
        print(f"ID: {p['id']} | Symbol: {p['symbol']} | Side: {p['side']} | Rule: {p['rule_code']} | Status: {p['status']} | Opened: {p['opened_at']} | Closed: {p['closed_at']}")
        
    print("\n--- 2. Bot State (Crypto) ---")
    state = sb.table("bot_state").select("*").execute()
    for s in state.data:
        print(s)
        
    print("\n--- 3. Recent Strategy Evaluations (Crypto) ---")
    # Let's search for evaluations. What is the name of the table? Is it strategy_evaluations? Let's check.
    try:
        evals = sb.table("strategy_evaluations").select("*").order("created_at", desc=True).limit(5).execute()
        for e in evals.data:
            print(f"Time: {e['created_at']} | Symbol: {e['symbol']} | Rule: {e['rule_code']} | Action: {e['action']}")
    except Exception as ex:
        print(f"Error checking evaluations: {ex}")

if __name__ == "__main__":
    check_crypto()
