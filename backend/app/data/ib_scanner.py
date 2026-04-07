"""
eTrader v4.5 — IB Scanner (Hot by Volume)
Capa 0: Universe Discovery using Interactive Brokers Market Scanner.

Replaces QWEN AI discovery with real-time IB Scanner data.
Uses reqScannerSubscription with HOT_BY_VOLUME scan code.

Flow:
  1. Connect to TWS/IB Gateway
  2. Request HOT_BY_VOLUME scanner (US stocks)
  3. Receive 30-50 tickers ranked by volume activity
  4. Save to watchlist_daily in Supabase
  5. Refresh every 5 minutes during market hours
"""
import asyncio
import os
import sys
import threading
import time
from datetime import date, datetime, timezone
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.data.ib_provider import get_ib_connection, IB_AVAILABLE

MODULE = "ib_scanner"

# Try importing IB API scanner classes
try:
    from ibapi.scanner import ScannerSubscription
    from ibapi.tag_value import TagValue
    IB_SCANNER_AVAILABLE = True
except ImportError:
    IB_SCANNER_AVAILABLE = False
    log_warning(MODULE, "ibapi not installed — IB Scanner features disabled")


# ── Scanner Result Storage ──────────────────────────────
_scanner_results: dict[int, list[dict]] = {}  # reqId -> list of results
_scanner_complete: dict[int, bool] = {}       # reqId -> scan complete flag
_scanner_lock = threading.Lock()
_SCANNER_REQ_ID = 9001  # Unique request ID for HOT_BY_VOLUME


class IBScannerMixin:
    """
    Mixin that adds scanner callback methods to IBConnection.
    Must be patched onto the existing IBConnection instance.
    """

    def scannerData(self, reqId, rank, contractDetails, distance, benchmark, projection, legsStr):
        """Called for each scanner result row."""
        with _scanner_lock:
            if reqId not in _scanner_results:
                _scanner_results[reqId] = []

            contract = contractDetails.contract
            _scanner_results[reqId].append({
                "rank": rank,
                "ticker": contract.symbol,
                "sec_type": contract.secType,
                "exchange": contract.primaryExchange or contract.exchange,
                "currency": contract.currency,
                "long_name": contractDetails.longName or "",
                "industry": contractDetails.industry or "",
                "category": contractDetails.category or "",
            })

    def scannerDataEnd(self, reqId):
        """Called when all scanner results have been delivered."""
        with _scanner_lock:
            _scanner_complete[reqId] = True
            count = len(_scanner_results.get(reqId, []))
        log_info(MODULE, f"Scanner #{reqId} complete: {count} results received")


def _patch_scanner_callbacks(ib_conn):
    """Patch scanner callback methods onto an existing IBConnection."""
    import types
    ib_conn.scannerData = types.MethodType(IBScannerMixin.scannerData, ib_conn)
    ib_conn.scannerDataEnd = types.MethodType(IBScannerMixin.scannerDataEnd, ib_conn)


async def scan_hot_by_volume(
    max_results: int = 50,
    min_price: float = 1.0,
    max_price: float = 300.0,
    min_volume: int = 700_000,
    min_market_cap: int = 500_000_000,
    timeout_s: float = 15.0,
) -> list[dict]:
    """
    Execute IB Scanner: HOT_BY_VOLUME for US stocks.

    Parameters
    ----------
    max_results : Max number of tickers to return (IB max = 50)
    min_price   : Minimum stock price filter
    max_price   : Maximum stock price filter
    min_volume  : Minimum average daily volume filter
    timeout_s   : Seconds to wait for scanner response

    Returns
    -------
    List of dicts with keys: rank, ticker, exchange, long_name, industry, etc.
    """
    if not IB_AVAILABLE or not IB_SCANNER_AVAILABLE:
        log_warning(MODULE, "IB API not available — cannot run scanner")
        return []

    ib = get_ib_connection()
    if ib is None:
        log_warning(MODULE, "IB connection not available")
        return []

    # Ensure connected
    if not ib.connected:
        log_info(MODULE, "Connecting to IB TWS for scanner...")
        connected = ib.connect_tws()
        if not connected:
            log_error(MODULE, "Failed to connect to IB TWS")
            return []

    # Patch scanner callbacks if not already done
    if not hasattr(ib, '_scanner_patched'):
        _patch_scanner_callbacks(ib)
        ib._scanner_patched = True

    # Create scanner subscription
    scan_sub = ScannerSubscription()
    scan_sub.instrument = "STK"
    scan_sub.locationCode = "STK.US.MAJOR"
    scan_sub.scanCode = "HOT_BY_VOLUME"
    scan_sub.numberOfRows = max_results

    # Filter options
    filter_options = []
    if min_price > 0:
        filter_options.append(TagValue("priceAbove", str(min_price)))
    if max_price < 999999:
        filter_options.append(TagValue("priceBelow", str(max_price)))
    if min_volume > 0:
        filter_options.append(TagValue("volumeAbove", str(min_volume)))
    if min_market_cap > 0:
        # IB expects value in Millions for this filter sometimes, or absolute for others. 
        # For HOT_BY_VOLUME we use absolute value for safety.
        filter_options.append(TagValue("marketCapAbove", str(min_market_cap)))

    # Clear previous results
    with _scanner_lock:
        _scanner_results[_SCANNER_REQ_ID] = []
        _scanner_complete[_SCANNER_REQ_ID] = False

    # Request scanner
    log_info(MODULE, f"Requesting HOT_BY_VOLUME scanner "
                     f"(max={max_results}, price=${min_price}-${max_price}, "
                     f"vol>={min_volume:,})...")

    try:
        ib.reqScannerSubscription(
            _SCANNER_REQ_ID,
            scan_sub,
            [],              # scannerSubscriptionOptions (empty)
            filter_options,
        )
    except Exception as e:
        log_error(MODULE, f"Failed to request scanner: {e}")
        return []

    # Wait for results
    start = time.time()
    while not _scanner_complete.get(_SCANNER_REQ_ID, False):
        if time.time() - start > timeout_s:
            log_warning(MODULE, f"Scanner timeout after {timeout_s}s")
            break
        await asyncio.sleep(0.2)

    # Cancel subscription (we want one-shot, not streaming)
    try:
        ib.cancelScannerSubscription(_SCANNER_REQ_ID)
    except:
        pass

    # Collect results
    with _scanner_lock:
        results = list(_scanner_results.get(_SCANNER_REQ_ID, []))

    if results:
        tickers_str = ", ".join(r["ticker"] for r in results[:10])
        log_info(MODULE, f"HOT_BY_VOLUME: {len(results)} tickers found. "
                         f"Top 10: {tickers_str}...")
    else:
        log_warning(MODULE, "Scanner returned 0 results")

    return results


async def save_scanner_to_watchlist(results: list[dict]) -> list[str]:
    """
    Save scanner results to watchlist_daily table.
    Replaces entire daily watchlist with fresh scanner data.

    Returns list of ticker symbols saved.
    """
    if not results:
        return []

    sb = get_supabase()
    today = date.today().isoformat()

    # Build rows
    rows = []
    for r in results:
        rows.append({
            "ticker": r["ticker"].upper(),
            "pool_type": "ib_scanner",
            "catalyst_score": max(1, 10 - r.get("rank", 50) // 5),  # Higher rank = higher score
            "catalyst_type": "HOT_BY_VOLUME",
            "market_regime": "scanner",
            "date": today,
            "hard_filter_pass": True,
        })

    try:
        # Delete previous scanner entries for today
        sb.table("watchlist_daily").delete().eq("date", today).execute()
        # Insert new
        sb.table("watchlist_daily").insert(rows).execute()
        log_info(MODULE, f"Saved {len(rows)} scanner tickers to watchlist_daily")
    except Exception as e:
        log_error(MODULE, f"Error saving scanner results: {e}")

    return [r["ticker"] for r in results]


# ── Fallback: Use Alpha Vantage Top Gainers/Losers ──────

async def fallback_top_movers(api_key: str | None = None) -> list[dict]:
    """
    Fallback when IB TWS is not connected.
    Uses Alpha Vantage TOP_GAINERS_LOSERS endpoint to get active stocks.
    """
    import requests

    api_key = api_key or os.getenv("ALPHAVANTAGE_API_KEY", "")
    if not api_key:
        log_warning(MODULE, "No Alpha Vantage API key for fallback scanner")
        return []

    try:
        resp = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TOP_GAINERS_LOSERS",
                "apikey": api_key,
            },
            timeout=15,
        )
        data = resp.json()

        results = []
        rank = 0

        # Combine most_actively_traded (best proxy for "hot by volume")
        for item in data.get("most_actively_traded", [])[:50]:
            ticker = item.get("ticker", "")
            if not ticker or "." in ticker:  # Skip non-standard symbols
                continue
            results.append({
                "rank": rank,
                "ticker": ticker,
                "exchange": "",
                "long_name": "",
                "industry": "",
                "category": "",
                "volume": int(item.get("volume", 0)),
                "price": float(item.get("price", 0)),
                "change_pct": item.get("change_percentage", "0%"),
            })
            rank += 1

        log_info(MODULE, f"Alpha Vantage fallback: {len(results)} active tickers")
        return results

    except Exception as e:
        log_error(MODULE, f"Fallback scanner failed: {e}")
        return []
