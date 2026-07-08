import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from app.stocks.universe_builder import UniverseBuilder

async def test_universe_builder():
    sys.stdout.reconfigure(encoding='utf-8')
    print("Initializing UniverseBuilder...")
    builder = UniverseBuilder()
    
    from app.workers.stocks_scheduler import get_stocks_config
    config = get_stocks_config()
    max_price = float(config.get("max_stock_price", config.get("scanner_max_price", 20.0)))
    min_cap = int(config.get("min_market_cap_usd", 1_000_000_000))
    min_vol = int(config.get("min_daily_volume", 1_000_000))
    watchlist_core_count = int(config.get("watchlist_core_count", 50))

    try:
        print(f"Starting build_daily_watchlist (DB Limit: ${max_price})...")
        candidates = await builder.build_daily_watchlist(
            max_price=max_price,
            min_price=1.0,
            min_market_cap=min_cap,
            min_volume=min_vol,
            max_results=watchlist_core_count
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
