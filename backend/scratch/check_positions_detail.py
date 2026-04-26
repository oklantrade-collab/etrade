
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append('c:/Fuentes/eTrade/backend')
load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.core.supabase_client import get_supabase

def check_positions_detail():
    sb = get_supabase()
    tickers = ['ELPW', 'IPWR', 'NOWL']
    
    print("--- STOCKS POSITIONS DETAIL ---")
    res = sb.table("stocks_positions").select("*").in_("ticker", tickers).execute()
    for row in res.data:
        print(f"Ticker: {row['ticker']}")
        for k, v in row.items():
            print(f"  {k}: {v}")
        print("-" * 20)

if __name__ == "__main__":
    check_positions_detail()
