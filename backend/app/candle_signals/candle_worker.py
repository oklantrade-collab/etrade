"""
ANTIGRAVITY · Candle Signal Worker v1.0
Motor principal de detección de señales por patrones de velas japonesas.

Polling:
  Crypto & Forex: cada 5 minutos
  Stocks: cada 2 minutos (solo en horario de mercado)

Temporalidades: 4H y 1D
Patrones: 26 algoritmos de detección
Acciones: BUY, SELL, HOLD

Un BUY o SELL en CUALQUIER temporalidad (4H o 1D) activa la ejecución.
"""

import asyncio
import os
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.core.crypto_symbols import normalize_crypto_symbol
from app.candle_signals.candle_patterns import CandlePatternDetector, CandleOHLC, PatternResult
from app.candle_signals.candle_builder import build_candle_from_ohlcv, build_candle_from_dataframe
from app.candle_signals.candle_execution import execute_candle_signal

MODULE = "candle_signal_worker"

# ─── ALERT DEDUPLICATION (M6) ────────────────────────────────────────────────
# Cooldown per (pair, timeframe) → prevents duplicate alerts within same candle
_alert_cache: dict[str, datetime] = {}

# Cooldown durations per timeframe
COOLDOWN_SECONDS = {
    "4H": 4 * 3600,   # 4 hours
    "1D": 24 * 3600,  # 24 hours
}


def _is_alert_recent(pair: str, tf: str) -> bool:
    """Check if we already emitted an alert for this pair+tf within cooldown."""
    key = f"{pair}_{tf}"
    last = _alert_cache.get(key)
    if last is None:
        return False
    cooldown = COOLDOWN_SECONDS.get(tf, 14400)
    return (datetime.now(timezone.utc) - last).total_seconds() < cooldown


def _mark_alert_emitted(pair: str, tf: str):
    """Mark that we emitted an alert for this pair+tf."""
    key = f"{pair}_{tf}"
    _alert_cache[key] = datetime.now(timezone.utc)


# Market configurations will be loaded dynamically from DB in each cycle


# Stocks loaded dynamically from DB


# ═══════════════════════════════════════════════════════════════════════════════
#  CRYPTO EVALUATION
# ═══════════════════════════════════════════════════════════════════════════════

async def evaluate_crypto_pair(pair: str, detector: CandlePatternDetector) -> list[dict]:
    """
    Evaluate a crypto pair for candle patterns on 4H and 1D.
    Uses Binance klines API for OHLCV data.
    """
    results = []
    norm_pair = normalize_crypto_symbol(pair)
    binance_symbol = norm_pair

    try:
        from app.execution.binance_connector import get_client
        client = get_client()

        for tf, interval, limit in [("4H", "4h", 10), ("1D", "1d", 10)]:
            try:
                klines = client.get_klines(symbol=binance_symbol, interval=interval, limit=limit)
                if not klines or len(klines) < 3:
                    continue

                # Build CandleOHLC objects from klines
                # Kline format: [open_time, open, high, low, close, volume, ...]
                candles = []
                for k in klines:
                    candles.append(CandleOHLC(
                        open=float(k[1]),
                        high=float(k[2]),
                        low=float(k[3]),
                        close=float(k[4]),
                        volume=float(k[5]),
                    ))

                if len(candles) < 2:
                    continue

                current = candles[-1]
                history = candles[:-1]

                # Calculate volume SMA20 approximation
                vol_sma = sum(c.volume for c in candles) / len(candles) if candles else None

                result = detector.evaluate(current, history, volume_sma20=vol_sma)

                if result.action in ("BUY", "SELL"):
                    if not _is_alert_recent(norm_pair, tf):
                        candle_data = {
                            "open": current.open,
                            "high": current.high,
                            "low": current.low,
                            "close": current.close,
                            "volume": current.volume,
                        }
                        results.append({
                            "pair": norm_pair,
                            "market": "crypto",
                            "timeframe": tf,
                            "pattern": result,
                            "candle_data": candle_data,
                        })
                        _mark_alert_emitted(norm_pair, tf)
                        log_info(MODULE,
                            f"🕯️ CRYPTO {result.action} {norm_pair} ({tf}) — "
                            f"{result.pattern_name} (conf: {result.confidence:.0f}%)"
                        )
                    else:
                        log_info(MODULE, f"⏸️ Cooldown activo: {norm_pair} {tf} — omitiendo duplicado")

            except Exception as e:
                log_warning(MODULE, f"Error evaluating {norm_pair} {tf}: {e}")

    except Exception as e:
        log_error(MODULE, f"Crypto evaluation failed for {norm_pair}: {e}")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  FOREX EVALUATION
# ═══════════════════════════════════════════════════════════════════════════════

async def evaluate_forex_pair(pair: str, detector: CandlePatternDetector) -> list[dict]:
    """
    Evaluate a forex pair using data from market_candles table (stored by forex_worker).
    """
    results = []
    sb = get_supabase()

    for tf in ["4H", "1D"]:
        tf_key = tf.lower().replace("h", "h").replace("d", "d")  # "4h", "1d"

        try:
            # Fetch the last 10 closed candles for this TF
            res = sb.table("market_candles") \
                .select("open, high, low, close, volume") \
                .eq("symbol", pair) \
                .eq("timeframe", tf_key) \
                .eq("is_closed", True) \
                .order("open_time", desc=True) \
                .limit(10) \
                .execute()

            rows = res.data or []
            if len(rows) < 3:
                continue

            # Reverse to chronological order (oldest first)
            rows.reverse()

            candles = [
                CandleOHLC(
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r.get("volume", 0)),
                )
                for r in rows
            ]

            current = candles[-1]
            history = candles[:-1]
            vol_sma = sum(c.volume for c in candles) / len(candles) if candles else None

            result = detector.evaluate(current, history, volume_sma20=vol_sma)

            if result.action in ("BUY", "SELL"):
                if not _is_alert_recent(pair, tf):
                    candle_data = {
                        "open": current.open,
                        "high": current.high,
                        "low": current.low,
                        "close": current.close,
                        "volume": current.volume,
                    }
                    results.append({
                        "pair": pair,
                        "market": "forex",
                        "timeframe": tf,
                        "pattern": result,
                        "candle_data": candle_data,
                    })
                    _mark_alert_emitted(pair, tf)
                    log_info(MODULE,
                        f"🕯️ FOREX {result.action} {pair} ({tf}) — "
                        f"{result.pattern_name} (conf: {result.confidence:.0f}%)"
                    )
                else:
                    log_info(MODULE, f"⏸️ Cooldown activo: {pair} {tf}")

        except Exception as e:
            log_warning(MODULE, f"Error evaluating forex {pair} {tf}: {e}")

    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  STOCKS EVALUATION
# ═══════════════════════════════════════════════════════════════════════════════

async def evaluate_stocks_ticker(ticker: str, detector: CandlePatternDetector) -> list[dict]:
    """
    Evaluate a stock ticker for candle patterns on 4H and 1D.
    Uses yfinance for data.
    """
    results = []

    try:
        import yfinance as yf
        t = yf.Ticker(ticker)

        for tf, interval, period in [("4H", "1h", "30d"), ("1D", "1d", "60d")]:
            try:
                hist = t.history(period=period, interval=interval)
                if hist is None or hist.empty or len(hist) < 5:
                    continue

                # For 4H: aggregate 4 × 1h candles into 4H candles
                if tf == "4H" and interval == "1h":
                    candles_4h = _aggregate_hourly_to_4h(hist)
                    if len(candles_4h) < 3:
                        continue
                    candles = candles_4h
                else:
                    # Daily candles — use directly
                    candles = []
                    for _, row in hist.tail(10).iterrows():
                        candles.append(CandleOHLC(
                            open=float(row["Open"]),
                            high=float(row["High"]),
                            low=float(row["Low"]),
                            close=float(row["Close"]),
                            volume=float(row.get("Volume", 0)),
                        ))

                if len(candles) < 2:
                    continue

                current = candles[-1]
                history = candles[:-1]
                vol_sma = sum(c.volume for c in candles) / len(candles) if candles else None

                result = detector.evaluate(current, history, volume_sma20=vol_sma)

                if result.action in ("BUY", "SELL"):
                    if not _is_alert_recent(ticker, tf):
                        candle_data = {
                            "open": current.open,
                            "high": current.high,
                            "low": current.low,
                            "close": current.close,
                            "volume": current.volume,
                        }

                        # Determine pool type from watchlist
                        pool = await _get_stock_pool_type(ticker)

                        results.append({
                            "pair": ticker,
                            "market": "stocks",
                            "timeframe": tf,
                            "pattern": result,
                            "candle_data": candle_data,
                            "pool_type": pool,
                        })
                        _mark_alert_emitted(ticker, tf)
                        log_info(MODULE,
                            f"🕯️ STOCKS {result.action} {ticker} ({tf}) — "
                            f"{result.pattern_name} (conf: {result.confidence:.0f}%) pool={pool}"
                        )
                    else:
                        log_info(MODULE, f"⏸️ Cooldown activo: {ticker} {tf}")

            except Exception as e:
                log_warning(MODULE, f"Error evaluating stock {ticker} {tf}: {e}")

    except Exception as e:
        log_error(MODULE, f"Stocks evaluation failed for {ticker}: {e}")

    return results


def _aggregate_hourly_to_4h(df) -> list[CandleOHLC]:
    """Aggregate 1h candles into 4h candles."""
    candles = []
    rows = list(df.iterrows())
    
    # Process in chunks of 4
    for i in range(0, len(rows) - 3, 4):
        chunk = rows[i:i+4]
        if len(chunk) < 4:
            break

        o = float(chunk[0][1]["Open"])
        h = max(float(r[1]["High"]) for r in chunk)
        l = min(float(r[1]["Low"]) for r in chunk)
        c = float(chunk[-1][1]["Close"])
        v = sum(float(r[1].get("Volume", 0)) for r in chunk)

        candles.append(CandleOHLC(open=o, high=h, low=l, close=c, volume=v))

    return candles


async def _get_stock_pool_type(ticker: str) -> str:
    """Get the pool type for a stock ticker from watchlist."""
    try:
        sb = get_supabase()
        res = sb.table("watchlist_daily") \
            .select("pool_type") \
            .eq("ticker", ticker) \
            .order("date", desc=True) \
            .limit(1) \
            .execute()

        if res.data:
            pool = res.data[0].get("pool_type", "")
            if pool and any(tag in pool.upper() for tag in ("GIANT", "LEADER", "PRO", "VALUE")):
                return "PRO"
        return "HOT"
    except Exception:
        return "HOT"


async def _get_stocks_watchlist() -> list[str]:
    """Get the active stocks watchlist for candle signal evaluation."""
    try:
        sb = get_supabase()
        from datetime import date
        today = date.today().isoformat()

        # Get today's watchlist entries
        res = sb.table("watchlist_daily") \
            .select("ticker") \
            .eq("date", today) \
            .eq("hard_filter_pass", True) \
            .order("catalyst_score", desc=True) \
            .limit(50) \
            .execute()

        tickers = set(r["ticker"] for r in (res.data or []))

        # Also include tickers with open positions
        pos_res = sb.table("stocks_positions").select("ticker").eq("status", "open").execute()
        for p in (pos_res.data or []):
            tickers.add(p["ticker"])

        if tickers:
            return list(tickers)

        # Fallback defaults
        return ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "AMD", "COIN", "PLTR"]

    except Exception:
        return ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"]


async def _get_crypto_watchlist() -> list[str]:
    """Get enabled crypto symbols from system config/whitelist."""
    try:
        sb = get_supabase()
        res = sb.table("trading_config").select("active_symbols").eq("id", 1).maybe_single().execute()
        if res.data and res.data.get("active_symbols"):
            syms = res.data["active_symbols"]
            if isinstance(syms, str):
                import json
                try:
                    syms = json.loads(syms)
                except:
                    syms = [s.strip() for s in syms.split(",") if s.strip()]
            
            out = [normalize_crypto_symbol(s) for s in syms if s and str(s).strip()]
            if out:
                return out
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]
    except Exception:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]


async def _get_forex_watchlist() -> list[str]:
    """Get active forex pairs from database."""
    try:
        sb = get_supabase()
        res = sb.table("bot_config").select("value").eq("key", "enabled_symbols_forex").maybe_single().execute()
        if res.data and res.data.get("value"):
            return res.data["value"] if isinstance(res.data["value"], list) else ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
        return ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
    except Exception:
        return ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]



# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN CYCLES
# ═══════════════════════════════════════════════════════════════════════════════

async def run_crypto_forex_cycle():
    """
    Single cycle for Crypto + Forex candle signal evaluation.
    Called every 5 minutes.
    """
    cycle_start = time.time()
    log_info(MODULE, "═══ CANDLE SIGNAL CYCLE (Crypto + Forex) START ═══")

    crypto_detector = CandlePatternDetector(market="crypto")
    forex_detector = CandlePatternDetector(market="forex")

    all_signals = []

    # ── CRYPTO ──
    crypto_pairs = await _get_crypto_watchlist()
    for pair in crypto_pairs:
        try:
            signals = await evaluate_crypto_pair(pair, crypto_detector)
            all_signals.extend(signals)
        except Exception as e:
            log_error(MODULE, f"Crypto pair {pair} failed: {e}")
        await asyncio.sleep(0.5)  # Rate limit

    # ── FOREX (only during market hours Mon-Fri) ──
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Mon, 6=Sun
    if weekday < 5:  # Mon-Fri
        forex_pairs = await _get_forex_watchlist()
        for pair in forex_pairs:
            try:
                signals = await evaluate_forex_pair(pair, forex_detector)
                all_signals.extend(signals)
            except Exception as e:
                log_error(MODULE, f"Forex pair {pair} failed: {e}")
            await asyncio.sleep(0.3)

    # ── EXECUTE SIGNALS ──
    executed_count = 0
    for sig in all_signals:
        try:
            result = execute_candle_signal(
                market=sig["market"],
                pair_or_ticker=sig["pair"],
                pattern=sig["pattern"],
                timeframe=sig["timeframe"],
                candle_data=sig["candle_data"],
                pool_type=sig.get("pool_type", ""),
            )
            if result.get("success"):
                executed_count += 1
        except Exception as e:
            log_error(MODULE, f"Execution failed for {sig['pair']}: {e}\n{traceback.format_exc()}")

    duration = round(time.time() - cycle_start, 1)
    log_info(MODULE,
        f"═══ CANDLE SIGNAL CYCLE END ═══ "
        f"Signals: {len(all_signals)} | Executed: {executed_count} | "
        f"Duration: {duration}s"
    )


async def run_stocks_candle_cycle():
    """
    Single cycle for Stocks candle signal evaluation.
    Called every 2 minutes during market hours.
    """
    # Check market hours
    try:
        from app.core.market_hours import is_market_open
        is_open, status = is_market_open()
        if not is_open:
            log_info(MODULE, f"Stocks candle cycle skipped — market {status}")
            return
    except Exception:
        pass  # If market_hours not available, run anyway

    cycle_start = time.time()
    log_info(MODULE, "═══ CANDLE SIGNAL CYCLE (Stocks) START ═══")

    detector = CandlePatternDetector(market="stocks")
    tickers = await _get_stocks_watchlist()

    all_signals = []
    for ticker in tickers:
        try:
            signals = await evaluate_stocks_ticker(ticker, detector)
            all_signals.extend(signals)
        except Exception as e:
            log_error(MODULE, f"Stock {ticker} failed: {e}")
        await asyncio.sleep(0.3)

    # Execute signals
    executed_count = 0
    for sig in all_signals:
        try:
            result = execute_candle_signal(
                market="stocks",
                pair_or_ticker=sig["pair"],
                pattern=sig["pattern"],
                timeframe=sig["timeframe"],
                candle_data=sig["candle_data"],
                pool_type=sig.get("pool_type", "HOT"),
            )
            if result.get("success"):
                executed_count += 1
        except Exception as e:
            err_msg = str(e)
            if "10061" in err_msg:
                err_msg = f"Connection Refused (10061). If using IB TWS, ensure it is open and API is enabled on port 7497. Original error: {err_msg}"
            log_error(MODULE, f"Stock execution failed for {sig['pair']}: {err_msg}")

    duration = round(time.time() - cycle_start, 1)
    log_info(MODULE,
        f"═══ CANDLE SIGNAL CYCLE (Stocks) END ═══ "
        f"Tickers: {len(tickers)} | Signals: {len(all_signals)} | "
        f"Executed: {executed_count} | Duration: {duration}s"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  SCHEDULER
# ═══════════════════════════════════════════════════════════════════════════════

async def start_candle_signal_scheduler():
    """
    Start the candle signal scheduler with APScheduler.
    
    Schedule:
      1. Crypto + Forex: every 5 minutes (24/7 for crypto, Mon-Fri for forex)
      2. Stocks: every 2 minutes (during market hours only)
    """
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = AsyncIOScheduler()

    # 1. CRYPTO + FOREX: every 5 minutes
    scheduler.add_job(
        run_crypto_forex_cycle,
        trigger=IntervalTrigger(minutes=5),
        id="candle_crypto_forex",
        name="Candle Signals - Crypto & Forex (5min)",
        max_instances=1,
        replace_existing=True,
    )

    # 2. STOCKS: every 2 minutes
    scheduler.add_job(
        run_stocks_candle_cycle,
        trigger=IntervalTrigger(minutes=2),
        id="candle_stocks",
        name="Candle Signals - Stocks (2min)",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.start()
    log_info(MODULE, "🕯️ Candle Signal Scheduler started — Crypto+Forex(5m) | Stocks(2m)")

    # Run first cycle immediately
    await run_crypto_forex_cycle()

    # Keep alive
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        log_info(MODULE, "Candle Signal Scheduler stopped")


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log_info(MODULE, "Starting Candle Signal Worker (standalone)...")
    asyncio.run(start_candle_signal_scheduler())
