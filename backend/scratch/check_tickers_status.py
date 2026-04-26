
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append('c:/Fuentes/eTrade/backend')
load_dotenv('c:/Fuentes/eTrade/backend/.env')

from app.core.supabase_client import get_supabase

def check_tickers():
    sb = get_supabase()
    tickers = ['ELPW', 'IPWR', 'NOWL']
    
    print("--- TRADE OPPORTUNITIES ---")
    res = sb.table("trade_opportunities").select("*").in_("ticker", tickers).execute()
    for row in res.data:
        print(f"ID: {row['id']} | Ticker: {row['ticker']} | Status: {row['status']} | Created: {row['created_at']} | Type: {row.get('trade_type')} | Meta Score: {row.get('meta_score')}")

    print("\n--- STOCKS ORDERS ---")
    res = sb.table("stocks_orders").select("*").in_("ticker", tickers).execute()
    for row in res.data:
        print(f"ID: {row['id']} | Ticker: {row['ticker']} | Status: {row['status']} | Type: {row['order_type']} | Direction: {row['direction']} | Created: {row['created_at']}")

    print("\n--- STOCKS POSITIONS ---")
    res = sb.table("stocks_positions").select("*").in_("ticker", tickers).execute()
    for row in res.data:
        print(f"ID: {row['id']} | Ticker: {row['ticker']} | Status: {row['status']} | Shares: {row['shares']} | Entry: {row['avg_price']} | Created: {row.get('first_buy_at')}")

    print("\n--- CURRENT ACTIVE POSITIONS COUNT ---")
    res = sb.table("stocks_positions").select("id").eq("status", "open").execute()
    print(f"Total open positions: {len(res.data)}")

    print("\n--- STOCKS CONFIG ---")
    res = sb.table("stocks_config").select("*").execute()
    for row in res.data:
        if row['key'] in ['max_simultaneous_positions', 'max_concurrent_positions', 'paper_mode_active', 'total_capital_usd', 'max_total_risk_pct', 'max_pct_per_trade']:
            print(f"{row['key']}: {row['value']}")

if __name__ == "__main__":
    check_tickers()
