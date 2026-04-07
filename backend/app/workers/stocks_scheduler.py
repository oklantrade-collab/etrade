"""
eTrader v4.5 — Stocks Scheduler (Worker)
Main worker for the Stocks module running 5-minute cycles during US market hours.

Market Hours (Eastern Time):
  - Pre-market scan: 09:00 ET
  - Market open: 09:30 ET
  - Market close: 16:00 ET
  - Post-market: until 16:30 ET

The worker:
  1. Downloads OHLCV data via yfinance (historical/swing)
  2. Calculates technical indicators (TA-Lib via 'ta')
  3. Calculates RVOL and volume spikes
  4. Estimates slippage and liquidity
  5. Upserts results to Supabase
  6. Triggers AI analysis pipelines when scores warrant (Sprint 6+)
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import numpy as np

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.workers.market_sweep import run_market_sweep

MODULE = "stocks_scheduler"

# ── Market Hours (Eastern Time) ──
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
PREMARKET_HOUR = 9
PREMARKET_MINUTE = 0


def is_market_hours() -> bool:
    """Check if current time is within US market hours (ET)."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from dateutil.tz import gettz as ZoneInfo

    now_et = datetime.now(ZoneInfo("US/Eastern"))

    # Skip weekends
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False

    current_minutes = now_et.hour * 60 + now_et.minute
    market_open = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE
    market_close = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE

    return market_open <= current_minutes < market_close


def is_premarket() -> bool:
    """Check if in pre-market window (09:00-09:30 ET)."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from dateutil.tz import gettz as ZoneInfo

    now_et = datetime.now(ZoneInfo("US/Eastern"))

    if now_et.weekday() >= 5:
        return False

    current_minutes = now_et.hour * 60 + now_et.minute
    premarket_start = PREMARKET_HOUR * 60 + PREMARKET_MINUTE
    market_open = MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MINUTE

    return premarket_start <= current_minutes < market_open


def get_stocks_config() -> dict:
    """Load stocks configuration from Supabase."""
    try:
        sb = get_supabase()
        res = sb.table("stocks_config").select("key, value").execute()
        config = {}
        for row in res.data:
            val = row["value"]
            # Auto-cast numeric values
            try:
                val = float(val)
                if val == int(val):
                    val = int(val)
            except (ValueError, TypeError):
                pass
            config[row["key"]] = val
        return config
    except Exception as e:
        log_warning(MODULE, f"Error loading stocks_config: {e}")
        return {
            "total_capital_usd": 5000,
            "paper_mode_active": True,
            "kill_switch_active": False,
        }


async def get_watchlist(config: dict) -> list[str]:
    """
    Get the active watchlist tickers.
    
    Priority:
    1. Today's watchlist_daily entries that passed hard_filter
    2. Fall back to core watchlist from config
    """
    sb = get_supabase()
    try:
        from datetime import date
        today = date.today().isoformat()

        res = sb.table("watchlist_daily")\
            .select("ticker")\
            .eq("date", today)\
            .eq("hard_filter_pass", True)\
            .order("catalyst_score", desc=True)\
            .limit(500)\
            .execute()


        if res.data and len(res.data) > 0:
            tickers = list(set(r["ticker"] for r in res.data))
            log_info(MODULE, f"Watchlist from DB: {len(tickers)} tickers")
            return tickers

    except Exception as e:
        log_warning(MODULE, f"Error loading watchlist from DB: {e}")

    # Fallback: default core tickers
    default_tickers = [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
        "META", "TSLA", "AMD", "INTC", "SOFI",
    ]
    log_info(MODULE, f"Using default watchlist: {len(default_tickers)} tickers")
    return default_tickers


async def process_ticker(ticker: str, config: dict) -> dict | None:
    from app.data.yfinance_provider import YFinanceProvider
    from app.analysis.stocks_indicators import calculate_stock_indicators

    try:
        provider = YFinanceProvider()
        
        # 1. DOWNLOAD MULTI-TIMEFRAME DATA
        df_15m = await provider.get_ohlcv(ticker, interval="15m", period="60d")
        df_4h = await provider.get_ohlcv(ticker, interval="1h", period="60d") 
        df_1d = await provider.get_ohlcv(ticker, interval="1d", period="300d")

        # ROBUST NULL CHECK — skip ticker entirely if any timeframe fails
        if df_15m is None or df_15m.empty or len(df_15m) < 10:
            log_warning(MODULE, f"Skipping {ticker}: no 15m data")
            return None
        if df_1d is None or df_1d.empty or len(df_1d) < 10:
            log_warning(MODULE, f"Skipping {ticker}: no 1d data")
            return None
        if df_4h is None or df_4h.empty or len(df_4h) < 2:
            log_warning(MODULE, f"Skipping {ticker}: no 4h/1h data")
            return None

        # 2. CALCULATE INDICATORS
        ind_15m = calculate_stock_indicators(df_15m, "15m", ticker)
        ind_1d = calculate_stock_indicators(df_1d, "1d", ticker)
        
        if not ind_15m or not ind_1d:
            log_warning(MODULE, f"Skipping {ticker}: indicator calculation failed")
            return None

        # 3. VOLUME FILTER (Min 1M)
        volume_24h = ind_1d.get("volume", 0)
        if volume_24h < 1000000:
            return None

        # 4. TECHNICAL RULES (SINGLE PASS — NO DUPLICATES)
        sar_1d = 1 if ind_1d.get("psar_direction") == "bullish" else 0
        candle_4h = 1 if df_4h.iloc[-1]["close"] > df_4h.iloc[-1]["open"] else 0

        # SCORING (T01: 40pts, T02: 30pts, T03: 20pts, T04: 10pts = 100 max)
        base_score = 40.0 if sar_1d > 0 else 10.0
        if ind_15m.get("ema_alignment") == "bullish": base_score += 30.0
        if candle_4h > 0: base_score += 20.0
        
        rsi_val = ind_15m.get("rsi_14")
        if rsi_val and 40 <= rsi_val <= 70:
            base_score += 10.0

        # PRO SCORING (P01: 40pts, P02: 30pts, P03: 20pts, P04: 10pts = 100 max) - 1D TIMEFRAME
        pro_score = 0.0
        ema_50_1d = ind_1d.get("ema_50") or 0.0
        ema_200_1d = ind_1d.get("ema_200") or 999999.0
        ema_20_1d = ind_1d.get("ema_20") or 0.0
        
        if ema_50_1d > ema_200_1d: pro_score += 40.0
        if ema_20_1d > ema_50_1d: pro_score += 30.0
        if ind_1d.get("psar_direction") == "bullish": pro_score += 20.0
        
        rsi_1d = ind_1d.get("rsi_14")
        if rsi_1d and rsi_1d <= 30.0:
            pro_score += 10.0

        # 5. CAPTURE LIVE PRICE & VOLUME
        current_price = float(df_15m["close"].iloc[-1])
        
        # 6. SAVE TO DB
        from app.analysis.stocks_indicators import upsert_technical_score
        is_acceptable = sar_1d > 0 and candle_4h > 0 and ind_15m.get("ema_alignment") == "bullish"
        upsert_technical_score(ticker, ind_15m, base_score, is_acceptable, pro_score)

        if is_acceptable:
            log_info(MODULE, f"🌟 {ticker} BULLISH ALIGNED (SAR+4H+EMA) Score={base_score} | Pro_Score={pro_score}")

        return {
            "ticker": ticker,
            "technical_score": base_score,
            "pro_score": pro_score,
            "rvol": ind_15m.get("rvol", 1.0),
            "price": float(current_price),
            "acceptable": is_acceptable,
        }

    except Exception as e:
        log_warning(MODULE, f"Skipping {ticker}: {e}")
        return None


async def run_stocks_cycle():
    """
    Main stocks cycle — runs every 5 minutes during market hours.
    """
    cycle_start = time.time()
    log_info(MODULE, "═══ STOCKS CYCLE START ═══")

    try:
        config = get_stocks_config()

        # Check kill switch
        if config.get("kill_switch_active", "false") == "true":
            log_warning(MODULE, "Kill switch ACTIVE — skipping cycle")
            return

        # Check market hours
        if not is_market_hours() and not is_premarket():
            log_info(MODULE, "Outside market hours — skipping cycle")
            return

        # ── CAPA 0: IB Scanner HOT_BY_VOLUME — Refresh universe every cycle ──
        scanner_max_price = float(config.get("scanner_max_price", 200))
        scanner_min_cap = int(config.get("scanner_min_market_cap", 500_000_000))
        
        try:
            from app.stocks.universe_builder import UniverseBuilder
            builder = UniverseBuilder()
            candidates = await builder.build_daily_watchlist(
                max_price=scanner_max_price, 
                min_market_cap=scanner_min_cap
            )
            if candidates:
                log_info(MODULE, f"IB Scanner: {len(candidates)} candidatos "
                                f"(max_price=${scanner_max_price} | min_cap=${scanner_min_cap/1e6:.0f}M)")
        except Exception as e:
            log_warning(MODULE, f"Scanner refresh skipped: {e}")

        # Get watchlist (populated by IB Scanner, limited to top 20)
        tickers = await get_watchlist(config)
        if not tickers:
            log_warning(MODULE, "Empty watchlist — nothing to process")
            return

        # Process tickers in parallel
        log_info(MODULE, f"🚀 Analyzing {len(tickers)} tickers in parallel...")
        tasks = [process_ticker(ticker, config) for ticker in tickers]
        
        # Run all tasks concurrently
        results_raw = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = []
        processed_count = 0
        for i, res in enumerate(results_raw):
            if isinstance(res, Exception):
                log_error(MODULE, f"Error analyzing {tickers[i]}: {res}")
            elif res:
                results.append(res)
                processed_count += 1

        log_info(MODULE, f"✅ Cycle finished: {processed_count} tickers analyzed/passed filters.")

        # Summary
        duration_s = round(time.time() - cycle_start, 1)
        high_score_count = sum(1 for r in results if r["technical_score"] >= 60)
        spike_count = sum(1 for r in results if r["rvol"] >= 2.5)

        log_info(MODULE,
                 f"═══ STOCKS CYCLE END ═══ "
                 f"Processed: {len(results)}/{len(tickers)} | "
                 f"High Score (≥60): {high_score_count} | "
                 f"Volume Spikes: {spike_count} | "
                 f"Duration: {duration_s}s")

        # ── Sprint 7: Execute pending opportunities & monitor positions ──
        try:
            from app.stocks.order_executor import OrderExecutor
            executor = OrderExecutor()
            exec_results = await executor.execute_pending_opportunities()
            if exec_results:
                log_info(MODULE, f"📊 Executed {len(exec_results)} trade(s)")
        except Exception as e:
            log_warning(MODULE, f"Execution step skipped: {e}")

        try:
            from app.stocks.position_monitor import PositionMonitor
            monitor = PositionMonitor()
            await monitor.check_all_positions()
        except Exception as e:
            log_warning(MODULE, f"Monitor step skipped: {e}")

        # Log cycle to system_logs
        sb = get_supabase()
        sb.table("system_logs").insert({
            "module": MODULE,
            "level": "INFO",
            "message": f"Stocks cycle completed: {len(results)} tickers processed",
            "context": str({
                "tickers_processed": len(results),
                "high_score_count": high_score_count,
                "spike_count": spike_count,
                "duration_s": duration_s,
            }),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

    except Exception as e:
        log_error(MODULE, f"Stocks cycle failed: {e}")


async def start_stocks_scheduler():
    """
    Start the stocks scheduler using APScheduler.
    Runs every 5 minutes during market hours.
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler()

    # 1. Main cycle: every 1 minute during market hours (FASTER REFRESH)
    scheduler.add_job(
        run_stocks_cycle,
        trigger=IntervalTrigger(minutes=1),
        id="stocks_1m_cycle",
        name="Stocks 1-minute cycle",
        max_instances=1,
        replace_existing=True,
    )

    # 2. MEGA BARRIDO DIARIO: 2 AM Lunes a Viernes
    scheduler.add_job(
        run_market_sweep,
        trigger=CronTrigger(day_of_week='mon-fri', hour=2, minute=0),
        id="daily_market_sweep",
        name="Market Sweep (All US Tickers < $200 + 1M Vol)",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.start()
    log_info(MODULE, "Stocks scheduler started (5m interval + 2am Daily Sweep)")

    # Run first cycle immediately
    await run_stocks_cycle()

    # Keep running
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        log_info(MODULE, "Stocks scheduler stopped")


if __name__ == "__main__":
    asyncio.run(start_stocks_scheduler())
