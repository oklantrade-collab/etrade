import asyncio
import os
import sys
from dotenv import load_dotenv

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))
load_dotenv('backend/.env')

from app.api.stocks import get_stocks_opportunities

async def test_api():
    print("Testing get_stocks_opportunities directly...")
    try:
        # We need to mock the request or just call the function if it doesn't depend on it
        # The function signature is: async def get_stocks_opportunities()
        res = await get_stocks_opportunities()
        print("API Response:")
        # Print first few opportunities to avoid clutter
        res_copy = res.copy()
        res_copy['opportunities'] = res_copy['opportunities'][:2]
        print(res_copy)
        
        if res.get("market_status", {}).get("status") == "ERROR":
            print("Detected ERROR status in response!")
            
    except Exception as e:
        print(f"Direct call failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_api())
