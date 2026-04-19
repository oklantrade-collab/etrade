import asyncio
import os
import sys

# Add backend to path
backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_path)
os.chdir(backend_path)

from app.workers.stocks_scheduler import process_ticker
from app.core.config import settings

async def debug_analysis():
    ticker = "SPIR"
    print(f"--- Debugging Analysis for {ticker} ---")
    config = {
        "min_daily_volume": 100000,
        "max_risk_per_trade": 0.01
    }
    
    # We simulate a partial worker run
    from app.data.yfinance_provider import YFinanceProvider
    from app.analysis.stocks_indicators import calculate_stock_indicators
    from app.stocks.decision_engine import DecisionEngine
    
    provider = YFinanceProvider()
    df_15m = await provider.get_ohlcv(ticker, interval="15m", period="5d")
    df_1d = await provider.get_ohlcv(ticker, interval="1d", period="30d")
    df_4h = await provider.get_ohlcv(ticker, interval="4h", period="15d")
    
    ind_15m = calculate_stock_indicators(df_15m, "15m", ticker)
    
    engine = DecisionEngine()
    wl_entry = {
        "ticker": ticker,
        "fundamental_score": 34.13,
        "pool_type": "PRO"
    }
    
    print("Executing full analysis...")
    result = await engine.execute_full_analysis(ticker, wl_entry, ind_15m)
    
    print("\n--- RESULT ---")
    import json
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    asyncio.run(debug_analysis())
