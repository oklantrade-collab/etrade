import asyncio
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

async def check_ticker(ticker):
    sb = get_supabase()
    res = sb.table('technical_scores').select('*').eq('ticker', ticker).order('timestamp', desc=True).limit(1).execute()
    if res.data:
        s = res.data[0]
        print(f"--- {ticker} SNAPSHOT ---")
        print(f"Timestamp: {s['timestamp']}")
        print(f"Technical Score: {s['technical_score']}")
        print(f"Pro Score: {s.get('pro_score')}")
        print(f"Pine Signal: {s.get('pinescript_signal')}")
        print(f"Signals JSON: {s.get('signals_json')}")
    else:
        print(f"No data for {ticker}")

if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "DRCT"
    asyncio.run(check_ticker(ticker))
