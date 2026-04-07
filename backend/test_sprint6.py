"""
eTrader v4.5 — Sprint 6 Integration Test
Run: python test_sprint6.py

Tests the full AI Decision Layer (Capas 0, 3, 4, 5).
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.stocks.universe_builder import UniverseBuilder
from app.stocks.fundamental_analyzer import FundamentalAnalyzer
from app.stocks.context_analyzer import ContextAnalyzer
from app.stocks.decision_engine import DecisionEngine

async def test_sprint6():
    print("=" * 60)
    print("  eTrader v4.5 — SPRINT 6 AI INTEGRATION TEST")
    print("=" * 60)
    print()

    # 1. Test Capa 0: Universe Builder (Gemini)
    try:
        builder = UniverseBuilder()
        print("🔍 Testing Capa 0: Gemini Universe Builder...")
        candidates = await builder.build_daily_watchlist()
        
        if candidates and len(candidates) > 0:
            ticker = candidates[0]["ticker"]
            print(f"✅ Capa 0 OK: Gemini suggested {len(candidates)} tickers. Target for test: {ticker}")
        else:
            print("⚠️ Capa 0: Gemini suggested 0 candidates (check API response). Using AAPL as fallback.")
            ticker = "AAPL"
            candidates = [{"ticker": "AAPL", "catalyst_type": "Market Leader", "catalyst_score": 8}]
    except Exception as e:
        print(f"❌ Capa 0 Failed: {e}")
        return

    # 2. Test Capa 3: Fundamental Analyzer
    try:
        funda = FundamentalAnalyzer()
        print(f"🧐 Testing Capa 3: Fundamental Analyzer for {ticker}...")
        res = await funda.analyze_ticker(ticker)
        assert res is not None, "Fundamental analysis returned None"
        print(f"✅ Capa 3 OK: Mode {res['valuation_mode']} | Price: ${res['current_price']} | MOS: {res['margin_of_safety']}%")
    except Exception as e:
        print(f"❌ Capa 3 Failed: {e}")
        return

    # 3. Test Capa 4: Context Analyzer (Gemini)
    try:
        ctx = ContextAnalyzer()
        print(f"📡 Testing Capa 4: Context Analyzer for {ticker}...")
        res = await ctx.analyze_context(ticker, candidates[0])
        assert "context_score" in res, "Context score missing"
        print(f"✅ Capa 4 OK: Sentiment: {res['sentiment_score']} | Context Score: {res['context_score']}")
    except Exception as e:
        print(f"❌ Capa 4 Failed: {e}")
        return

    # 4. Test Capa 5: Decision Engine (Claude 3.5 Sonnet)
    try:
        engine = DecisionEngine()
        print(f"🧠 Testing Capa 5: Claude decision for {ticker}...")
        decision = await engine.execute_full_analysis(ticker, candidates[0])
        
        if decision:
            print(f"✅ Capa 5 OK: Decision: {decision.get('decision')} | Quadrant: {decision.get('quadrant')} | MetaScore: {decision.get('meta_score')}")
            if decision.get("decision") == "ENTER":
                setup = decision.get("trade_setup", {})
                print(f"   🚀 SETUP: Entry={setup.get('entry_zone_low')} - SL={setup.get('stop_loss')} - TP={setup.get('target_1')}")
        else:
            print("❌ Capa 5 Failed: Decision was None (Check logs for Technical Score missing in DB).")
    except Exception as e:
        print(f"❌ Capa 5 Failed: {e}")

    print()
    print("=" * 60)
    print("  Sprint 6 — AI Infrastructure Test Completed!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_sprint6())
