
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append('c:/Fuentes/eTrade/backend')
load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.core.supabase_client import get_supabase

def check_journal():
    sb = get_supabase()
    tickers = ['ELPW', 'IPWR', 'NOWL']
    
    print("--- TRADES JOURNAL ---")
    try:
        res = sb.table("trades_journal").select("*").in_("ticker", tickers).execute()
        if not res.data:
            print("No entries found in trades_journal for these tickers.")
        for row in res.data:
            print(f"Ticker: {row['ticker']} | Exit Date: {row['exit_date']} | PnL: {row.get('pnl_usd')}")
    except Exception as e:
        print(f"Error querying trades_journal: {e}")

if __name__ == "__main__":
    check_journal()
