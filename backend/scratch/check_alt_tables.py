
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append('c:/Fuentes/eTrade/backend')
load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.core.supabase_client import get_supabase

def check_alternative_tables():
    sb = get_supabase()
    tickers = ['ELPW', 'IPWR', 'NOWL']
    
    for table in ['trades_active', 'trades_journal', 'positions', 'orders']:
        print(f"--- {table.upper()} ---")
        try:
            res = sb.table(table).select("*").in_("ticker", tickers).execute()
            if not res.data:
                print(f"No entries found in {table}.")
            else:
                for row in res.data:
                    print(f"Ticker: {row['ticker']} | Status: {row.get('status')} | ID: {row.get('id')}")
        except Exception as e:
            print(f"Error querying {table}: {e}")

if __name__ == "__main__":
    check_alternative_tables()
