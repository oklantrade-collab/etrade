"""
eTrader v2 — Market API endpoints
"""
from fastapi import APIRouter, Query, Path
from app.core.supabase_client import get_supabase
from app.core.config import EXCLUDED_SYMBOLS
from app.analysis.data_fetcher import to_internal_symbol
from datetime import datetime, timezone, timedelta

router = APIRouter()


# Internal exclusion list (internal format)
_EXCLUDED_INTERNAL = [to_internal_symbol(s) for s in EXCLUDED_SYMBOLS]


@router.get("/symbols")
def get_symbols():
    """Get active symbols with latest data, excluding stablecoins."""
    sb = get_supabase()
    try:
        # Get unique symbols from recent candles
        result = (
            sb.table("market_candles")
            .select("symbol, timeframe, volume, close, open_time")
            .eq("timeframe", "15m")
            .order("open_time", desc=True)
            .limit(500)
            .execute()
        )
        # Group by symbol, take latest candle
        map_sym = {}
        for c in result.data:
            sym = c["symbol"]
            # Exclude stablecoins
            if sym in _EXCLUDED_INTERNAL:
                continue
            if sym not in map_sym:
                map_sym[sym] = c

        symbols = sorted(map_sym.values(), key=lambda x: float(x.get("volume", 0)), reverse=True)
        return {"symbols": symbols, "count": len(symbols)}
    except Exception as e:
        return {"error": str(e), "symbols": [], "count": 0}


@router.get("/candles/{symbol:path}")
def get_candles(
    symbol: str,
    timeframe: str = Query(default="15m"),
    limit: int = Query(default=100, le=500),
):
    """Get OHLC candles for a symbol (symbol can contain '/')."""
    sb = get_supabase()
    # Standardized: No slash format (BTCUSDT)
    symbol_clean = symbol.replace('/', '')

    result = (
        sb.table("market_candles")
        .select("open_time, open, high, low, close, volume, is_closed, basis, upper_1, upper_2, upper_3, upper_4, upper_5, upper_6, lower_1, lower_2, lower_3, lower_4, lower_5, lower_6, pinescript_signal, sar, sar_trend")
        .eq("symbol", symbol_clean)
        .eq("timeframe", timeframe)
        .order("open_time", desc=True)
        .limit(limit)
        .execute()
    )
    # Return in ascending order for charting
    candles = sorted(result.data, key=lambda x: x["open_time"])

    # Fallback for Stocks (yfinance)
    if not candles and len(symbol_clean) <= 5:
        try:
            import yfinance as yf
            import pandas as pd
            
            # Map timeframe to yfinance format
            yf_tf = timeframe
            if timeframe == "1d": yf_tf = "1d"
            elif timeframe == "1h": yf_tf = "1h"
            elif timeframe == "15m": yf_tf = "15m"
            
            ticker = yf.Ticker(symbol_clean)
            df = ticker.history(period="60d", interval=yf_tf)
            
            if not df.empty:
                for idx, row in df.iterrows():
                    candles.append({
                        "open_time": idx.isoformat(),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(row["Volume"]),
                        "basis": 0, "upper_6": 0, "lower_6": 0 # Default indicators
                    })
        except Exception as e:
            print(f"YFinance fallback error: {e}")

    return {"candles": candles, "symbol": symbol, "timeframe": timeframe}

@router.get("/trade-events/{symbol:path}")
def get_trade_events(
    symbol: str,
    days: int = Query(default=15, le=60)
):
    """Get entries, exits and blocked signals for charting markers from ALL markets."""
    sb = get_supabase()
    symbol_clean = symbol.replace('/', '')
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    def to_ts(val):
        if not val: return 0
        if isinstance(val, str):
            try:
                base = val.replace('Z', '').split('.')[0].split('+')[0]
                if 'T' not in base: base = base.replace(' ', 'T')
                dt = datetime.strptime(base[:19], '%Y-%m-%dT%H:%M:%S')
                return int(dt.replace(tzinfo=timezone.utc).timestamp())
            except: return 0
        try: return int(val.timestamp())
        except: return 0

    events = []

    # 1. CRYPTO
    try:
        crypto_res = sb.table('paper_trades').select('*').eq('symbol', symbol_clean).gte('opened_at', cutoff).execute().data or []
        for t in crypto_res:
            events.append({
                'type': 'entry', 'direction': t.get('side', 'long'), 'timestamp': to_ts(t.get('opened_at')),
                'price': float(t.get('entry_price', 0) or 0), 'rule_code': t.get('rule_code', '—'), 'blocked_reason': None
            })
            if t.get('closed_at'):
                reason = (t.get('close_reason') or '').lower()
                etype = 'tp_partial' if 'tp_partial' in reason else ('sl' if 'sl' in reason else 'tp_full')
                events.append({
                    'type': etype, 'direction': t.get('side', 'long'), 'timestamp': to_ts(t.get('closed_at')),
                    'price': float(t.get('exit_price', 0) or 0), 'rule_code': t.get('rule_code', '—'), 'blocked_reason': None
                })
    except Exception as e: print(f"Error Crypto events: {e}")

    # 2. FOREX
    try:
        forex_res = sb.table('forex_positions').select('*').eq('symbol', symbol_clean).gte('opened_at', cutoff).execute().data or []
        for t in forex_res:
            side = 'long' if str(t.get('side', 'long')).lower() in ['long', 'buy'] else 'short'
            events.append({
                'type': 'entry', 'direction': side, 'timestamp': to_ts(t.get('opened_at')),
                'price': float(t.get('entry_price', 0) or 0), 'rule_code': t.get('rule_code', '—'), 'blocked_reason': None
            })
            if t.get('closed_at'):
                reason = (t.get('close_reason') or '').lower()
                etype = 'sl' if 'sl' in reason else 'tp_full'
                events.append({
                    'type': etype, 'direction': side, 'timestamp': to_ts(t.get('closed_at')),
                    'price': float(t.get('current_price', 0) or 0), 'rule_code': t.get('rule_code', '—'), 'blocked_reason': None
                })
    except Exception as e: print(f"Error Forex events: {e}")

    # 3. STOCKS
    try:
        stocks_res = sb.table('stocks_positions').select('*').eq('ticker', symbol_clean).gte('opened_at', cutoff).execute().data or []
        for t in stocks_res:
            events.append({
                'type': 'entry', 'direction': 'long', 'timestamp': to_ts(t.get('opened_at')),
                'price': float(t.get('avg_price', 0) or 0), 'rule_code': t.get('rule_code', '—'), 'blocked_reason': None
            })
    except Exception as e: print(f"Error Stocks events: {e}")

    # 4. BLOCKED
    try:
        blocked_sigs = sb.table('trading_signals').select('*').eq('symbol', symbol_clean).eq('status', 'blocked').gte('created_at', cutoff).execute().data or []
        for b in blocked_sigs:
            events.append({
                'type': 'blocked', 'direction': b.get('signal_type', 'long'), 'timestamp': to_ts(b.get('created_at')),
                'price': float(b.get('entry_price', 0) or 0), 'rule_code': b.get('rule_code', '—'),
                'blocked_reason': b.get('blocked_reason')
            })
    except Exception as e: print(f"Error Blocked events: {e}")

    # Final sort
    try:
        events.sort(key=lambda x: x['timestamp'])
    except Exception as e:
        print(f"Error sorting events: {e}")

    return events


@router.get("/indicators/{symbol:path}")
def get_indicators(
    symbol: str,
    timeframe: str = Query(default="15m"),
    limit: int = Query(default=1, le=200),
):
    """Get technical indicators for a symbol (symbol can contain '/')."""
    sb = get_supabase()
    result = (
        sb.table("technical_indicators")
        .select("*")
        .eq("symbol", symbol)
        .eq("timeframe", timeframe)
        .order("timestamp", desc=True)
        .limit(limit)
        .execute()
    )
    # For limit > 1, return in ascending order for charting
    data = result.data
    if limit > 1:
        data = sorted(data, key=lambda x: x["timestamp"])

    return {"indicators": data, "symbol": symbol, "timeframe": timeframe}
