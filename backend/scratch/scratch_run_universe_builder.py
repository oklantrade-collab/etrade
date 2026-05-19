import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from app.stocks.universe_builder import UniverseBuilder

async def test_universe_builder():
    sys.stdout.reconfigure(encoding='utf-8')
    print("Initializing UniverseBuilder...")
    builder = UniverseBuilder()
    
    try:
        print("Starting build_daily_watchlist...")
        candidates = await builder.build_daily_watchlist(
            max_price=20.0,
            min_price=1.0,
            min_market_cap=1_000_000_000,
            min_volume=1_000_000,
            max_results=50
        )
        print("\n=== SCAN COMPLETED SUCCESSFULY ===")
        print(f"Total candidates found: {len(candidates)}")
        
        if candidates:
            print("\n--- FIRST 5 CANDIDATES ---")
            for c in candidates[:5]:
                print(f"  Ticker: {c['ticker']} | Price: {c.get('_price')} | Vol: {c.get('_volume')} | Fund Score: {c.get('fundamental_score')} | Pool: {c.get('pool_type')}")
        else:
            print("No candidates were found.")
            
    except Exception as e:
        print(f"\n❌ ERROR running build_daily_watchlist: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_universe_builder())
