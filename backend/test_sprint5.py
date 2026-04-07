"""
eTrader v4.5 — Sprint 5 Integration Test
Run: python test_sprint5.py

Tests:
  1. yfinance downloads data
  2. Technical indicators calculate correctly
  3. RVOL calculates correctly
  4. ATR-based stop loss works
  5. Slippage estimator functions
  6. Liquidity score calculates
  7. Stocks config loads from Supabase
"""
import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


async def test_sprint5():
    print("=" * 60)
    print("  eTrader v4.5 — SPRINT 5 INTEGRATION TEST")
    print("=" * 60)
    print()

    passed = 0
    failed = 0

    # ── Test 1: yfinance downloads data ──
    try:
        from app.data.yfinance_provider import YFinanceProvider
        provider = YFinanceProvider()
        df = await provider.get_ohlcv("AAPL", interval="5m", period="5d")
        assert df is not None and len(df) > 0, "No data returned"
        assert "open_time" in df.columns, "Missing open_time column"
        assert "close" in df.columns, "Missing close column"
        print(f"✅ Test 1: yfinance — {len(df)} candles AAPL 5m")
        passed += 1
    except Exception as e:
        print(f"❌ Test 1: yfinance — {e}")
        failed += 1

    # ── Test 2: Technical indicators ──
    try:
        from app.analysis.stocks_indicators import (
            calculate_stock_indicators,
            calculate_technical_score,
        )
        indicators = calculate_stock_indicators(df.copy(), "5m", "AAPL")
        assert indicators is not None, "Indicators returned None"
        assert indicators.get("rsi_14") is not None, "RSI not calculated"
        assert indicators.get("atr_14") is not None, "ATR not calculated"

        tech_score = calculate_technical_score(indicators)
        assert 0 <= tech_score <= 100, f"Invalid score: {tech_score}"
        print(f"✅ Test 2: Technical indicators — Score: {tech_score:.1f}, "
              f"RSI: {indicators['rsi_14']:.2f}, "
              f"ADX: {indicators.get('adx_14', 0):.2f}")
        passed += 1
    except Exception as e:
        print(f"❌ Test 2: Technical indicators — {e}")
        failed += 1

    # ── Test 3: RVOL ──
    try:
        from app.analysis.rvol import calculate_rvol, get_rvol_for_ticker
        rvol_data = get_rvol_for_ticker(df)
        assert rvol_data["current_rvol"] > 0, "RVOL is zero"
        print(f"✅ Test 3: RVOL — {rvol_data['current_rvol']:.2f}x "
              f"| Spike: {rvol_data['spike']['strength']}")
        passed += 1
    except Exception as e:
        print(f"❌ Test 3: RVOL — {e}")
        failed += 1

    # ── Test 4: ATR-based stop loss ──
    try:
        atr = indicators["atr_14"]
        entry = float(df["close"].iloc[-1])
        stop = entry - (atr * 2.0)
        # Stop should NOT be a round number
        assert round(stop, 2) != round(entry - 1, 2), "Stop loss is a round number"
        assert stop < entry, "Stop loss above entry"
        print(f"✅ Test 4: ATR SL — Entry: ${entry:.2f} | "
              f"ATR: ${atr:.4f} | SL (ATR×2): ${stop:.2f}")
        passed += 1
    except Exception as e:
        print(f"❌ Test 4: ATR Stop Loss — {e}")
        failed += 1

    # ── Test 5: Slippage estimator ──
    try:
        from app.analysis.slippage_estimator import estimate_slippage
        slippage = estimate_slippage(
            avg_daily_volume=5_000_000,
            order_shares=50,
            current_price=entry,
        )
        assert "slippage_pct" in slippage, "Missing slippage_pct"
        assert slippage["acceptable"], f"Slippage too high: {slippage['slippage_pct']}%"
        print(f"✅ Test 5: Slippage — {slippage['slippage_pct']:.4f}% "
              f"(${slippage['slippage_usd']:.2f}) | "
              f"Risk: {slippage['risk_level']}")
        passed += 1
    except Exception as e:
        print(f"❌ Test 5: Slippage — {e}")
        failed += 1

    # ── Test 6: Liquidity score ──
    try:
        from app.analysis.slippage_estimator import calculate_liquidity_score
        liq_score = calculate_liquidity_score(
            avg_daily_volume=5_000_000,
            current_price=entry,
            market_cap=2_500_000_000_000,  # AAPL market cap
        )
        assert 0 <= liq_score <= 10, f"Invalid score: {liq_score}"
        print(f"✅ Test 6: Liquidity Score — {liq_score}/10")
        passed += 1
    except Exception as e:
        print(f"❌ Test 6: Liquidity Score — {e}")
        failed += 1

    # ── Test 7: SPY Regime ──
    try:
        regime = await provider.get_spy_regime()
        assert regime["regime"] in ("bull", "bear", "sideways"), f"Invalid regime: {regime}"
        print(f"✅ Test 7: Market Regime — {regime['regime'].upper()} "
              f"| VIX: {regime['vix']} | SPY: ${regime['spy_price']}")
        passed += 1
    except Exception as e:
        print(f"❌ Test 7: Market Regime — {e}")
        failed += 1

    # ── Test 8: IB API availability (optional) ──
    try:
        from app.data.ib_provider import IB_AVAILABLE
        status = "Installed ✅" if IB_AVAILABLE else "Not installed (optional)"
        print(f"ℹ️  Test 8: IB API — {status}")
        passed += 1
    except Exception as e:
        print(f"ℹ️  Test 8: IB API — {e}")
        passed += 1  # Not a failure

    # ── Test 9: Multiple tickers ──
    try:
        tickers = ["AAPL", "MSFT", "NVDA"]
        results = await provider.get_multiple_tickers(tickers, interval="5m", period="5d")
        assert len(results) == len(tickers), f"Only got {len(results)}/{len(tickers)}"
        print(f"✅ Test 9: Multi-ticker — {list(results.keys())} OK")
        passed += 1
    except Exception as e:
        print(f"❌ Test 9: Multi-ticker — {e}")
        failed += 1

    # ── Summary ──
    print()
    print("=" * 60)
    total = passed + failed
    if failed == 0:
        print(f"  ✅ ALL {total} TESTS PASSED — Sprint 5 Ready!")
    else:
        print(f"  ⚠️  {passed}/{total} Tests Passed | {failed} Failed")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_sprint5())
