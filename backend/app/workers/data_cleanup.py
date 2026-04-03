"""
eTrade v3 — Data Cleanup Worker
Retention policy: cleans old OHLCV data based on timeframe.
Runs once per day at 00:00 UTC.
"""
from datetime import datetime, timedelta, timezone

from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error

MODULE = "data_cleanup"

RETENTION_POLICY = {
    "5m": 20,      # days — emergency alerts
    "15m": 60,     # days — primary signals
    "30m": 90,     # days
    "1h": 120,     # days (replaces 45m)
    "4h": 365,     # days — 1 year
    "1d": 1095,    # days — 3 years (covers EMA200)
    "1w": 2190,    # days — 6 years (covers weekly EMA200)
}


async def cleanup_old_ohlcv() -> dict:
    """
    Delete old candle data based on retention policy per timeframe.
    Estimated storage with 4 symbols: ~21 MB (well under Supabase free tier 500 MB).

    Returns
    -------
    dict with total_deleted count per timeframe
    """
    sb = get_supabase()
    results = {}

    for timeframe, days in RETENTION_POLICY.items():
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            cutoff_str = cutoff.isoformat()

            result = (
                sb.table("market_candles")
                .delete()
                .eq("timeframe", timeframe)
                .lt("open_time", cutoff_str)
                .execute()
            )

            deleted = len(result.data) if result.data else 0
            results[timeframe] = deleted

            if deleted > 0:
                log_info(
                    MODULE,
                    f"Cleaned {deleted} candles for {timeframe} (older than {days} days)",
                )
        except Exception as e:
            log_error(MODULE, f"Cleanup failed for {timeframe}: {e}")
            results[timeframe] = -1

    # Also clean old system logs (keep 30 days)
    try:
        log_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        sb.table("system_logs").delete().lt(
            "created_at", log_cutoff.isoformat()
        ).execute()
        log_info(MODULE, "Cleaned old system logs (30+ days)")
    except Exception as e:
        log_error(MODULE, f"Log cleanup failed: {e}")

    # Clean old indicator data
    try:
        for tf, days in RETENTION_POLICY.items():
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            sb.table("technical_indicators").delete().eq(
                "timeframe", tf
            ).lt("timestamp", cutoff.isoformat()).execute()
    except Exception as e:
        log_error(MODULE, f"Indicator cleanup failed: {e}")

    # Clean expired cooldowns
    try:
        sb.table("cooldowns").delete().eq("active", False).execute()
        log_info(MODULE, "Cleaned expired cooldowns")
    except Exception as e:
        log_error(MODULE, f"Cooldown cleanup failed: {e}")

    # Clean old regime history (keep 90 days)
    try:
        regime_cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        sb.table("market_regime_history").delete().lt(
            "evaluated_at", regime_cutoff.isoformat()
        ).execute()
    except Exception as e:
        log_error(MODULE, f"Regime history cleanup failed: {e}")

    total = sum(v for v in results.values() if v > 0)
    log_info(MODULE, f"Data cleanup complete: {total} total records deleted", results)
    return results


def run_cleanup():
    """Synchronous wrapper for the cleanup function."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(cleanup_old_ohlcv())
    finally:
        loop.close()
