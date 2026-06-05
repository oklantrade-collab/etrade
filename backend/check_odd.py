import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.core.supabase_client import get_supabase

def main():
    sb = get_supabase()
    
    print("--- stocks_orders for ODD ---")
    orders = sb.table("stocks_orders").select("*").eq("ticker", "ODD").order("created_at", desc=True).limit(5).execute()
    for o in orders.data:
        print(o)
        
    print("\n--- stocks_positions for ODD ---")
    pos = sb.table("stocks_positions").select("*").eq("ticker", "ODD").order("first_buy_at", desc=True).limit(5).execute()
    for p in pos.data:
        print(p)

    print("\n--- trades_journal for ODD ---")
    journal = sb.table("trades_journal").select("*").eq("ticker", "ODD").order("exit_date", desc=True).limit(5).execute()
    for j in journal.data:
        print(j)

if __name__ == "__main__":
    main()
