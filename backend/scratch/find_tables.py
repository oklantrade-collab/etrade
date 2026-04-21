import os, sys, asyncio, json
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.supabase_client import get_supabase

async def find_tables():
    sb = get_supabase()
    # Try to guess common names
    tables = ['forex_positions', 'positions', 'paper_trades', 'orders', 'forex_orders', 'candle_signals', 'market_snapshot', 'forex_execution_logs', 'trading_logs', 'logs']
    for t in tables:
        try:
            res = sb.table(t).select('*').limit(1).execute()
            print(f"Table '{t}' exists.")
        except:
            print(f"Table '{t}' does NOT exist.")

if __name__ == "__main__":
    asyncio.run(find_tables())
