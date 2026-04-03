
import os
import asyncio
from dotenv import load_dotenv
from app.core.supabase_client import get_supabase

load_dotenv('.env')

async def check():
    sb = get_supabase()
    
    print("--- CHECK 1: MTF Score ---")
    res = sb.table("market_snapshot").select("symbol, mtf_score, updated_at").order("symbol").execute()
    for row in res.data:
        print(f"Symbol: {row['symbol']}, MTF Score: {row['mtf_score']}, Updated At: {row['updated_at']}")
        
    print("\n--- CHECK 4: Regime Entry ---")
    res = sb.table("positions").select("symbol, regime_entry, status").eq("status", "open").execute()
    for row in res.data:
        print(f"Symbol: {row['symbol']}, Regime Entry: {row['regime_entry']}")
        
    print("\n--- CHECK 6: ADA Zone ---")
    res = sb.table("market_snapshot").select("symbol, price, basis, lower_4, lower_5, lower_6, fibonacci_zone").eq("symbol", "ADAUSDT").execute()
    if res.data:
        row = res.data[0]
        print(f"Price: {row['price']}")
        print(f"Lower 4: {row['lower_4']}")
        print(f"Lower 5: {row['lower_5']}")
        print(f"Lower 6: {row['lower_6']}")
        print(f"Fibonacci Zone: {row['fibonacci_zone']}")
    else:
        print("ADAUSDT not found in snapshot")

if __name__ == "__main__":
    asyncio.run(check())
