import sys
sys.path.append('.')
from app.stocks.decision_engine import DecisionEngine
import asyncio

async def test():
    engine = DecisionEngine()
    try:
        await engine.execute_full_analysis("AAPL", {}, {})
        print("SUCCESS")
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")

asyncio.run(test())
