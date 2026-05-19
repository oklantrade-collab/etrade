import asyncio
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
load_dotenv('backend/.env')

from app.api.stocks import get_stocks_opportunities

async def test_api():
    print("Testing get_stocks_opportunities directly (Cleaned output)...")
    try:
        res = await get_stocks_opportunities()
        print(f"Market Status: {res.get('market_status', {}).get('status')}")
        print(f"Total Opportunities: {res.get('total')}")
        print(f"Opportunities count in list: {len(res.get('opportunities', []))}")
        
        if res.get('opportunities'):
            first = res['opportunities'][0]
            print(f"First ticker: {first.get('ticker')}")
            # Safely print keys
            print(f"Keys in first item: {list(first.keys())}")
            
    except Exception as e:
        print(f"Direct call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_api())
