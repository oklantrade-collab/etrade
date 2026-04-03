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
    return {"candles": candles, "symbol": symbol, "timeframe": timeframe}



@router.get("/trade-events/{symbol:path}")
def get_trade_events(
    symbol: str,
    days: int = Query(default=7, le=60)
):
    """Get entries, exits and blocked signals for charting markers."""
    sb = get_supabase()
    
    # We'll use a raw SQL query or standard selects + manual union
    # Let's use selects to be safer with supabase-py
    
    symbol_clean = symbol.replace('/', '')
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    # 1. Entries from paper_trades
    entries = sb.table('paper_trades') \
        .select('side, opened_at, entry_price, rule_code') \
        .eq('symbol', symbol_clean) \
        .gte('opened_at', cutoff) \
        .execute().data
    
    # 2. Exits from paper_trades
    exits = sb.table('paper_trades') \
        .select('side, closed_at, exit_price, rule_code, close_reason') \
        .eq('symbol', symbol_clean) \
        .not_.is_('closed_at', 'null') \
        .gte('closed_at', cutoff) \
        .execute().data
    
    def to_ts(val):
        if not val: return 0
        if isinstance(val, str):
            try:
                # Robust parsing for ISO strings like '2026-04-02T08:05:12.58942+00:00'
                # Truncate to seconds for simplicity in charting
                base = val.replace('Z', '').split('.')[0].split('+')[0]
                if 'T' not in base: base = base.replace(' ', 'T')
                dt = datetime.strptime(base[:19], '%Y-%m-%dT%H:%M:%S')
                return int(dt.replace(tzinfo=timezone.utc).timestamp())
            except Exception:
                return 0
        try:
            return int(val.timestamp())
        except:
            return 0

    events = []
    
    # 3. Blocked signals from signals_log OR trading_signals
    try:
        # Intentar primero con signals_log (si existe)
        blocked_res = sb.table('signals_log') \
            .select('*') \
            .eq('symbol', symbol_clean) \
            .gte('detected_at', cutoff) \
            .execute().data
        if blocked_res:
            for b in blocked_res:
                events.append({
                    'type': 'blocked',
                    'direction': b.get('direction', 'long'),
                    'timestamp': to_ts(b.get('detected_at')),
                    'price': float(b.get('price', 0) or 0),
                    'rule_code': b.get('rule_code', '—'),
                    'blocked_reason': b.get('reason_skip') or b.get('message')
                })
    except:
        pass

    try:
        # También buscar en trading_signals con status='blocked'
        blocked_sigs = sb.table('trading_signals') \
            .select('*') \
            .eq('symbol', symbol_clean) \
            .eq('status', 'blocked') \
            .gte('created_at', cutoff) \
            .execute().data
        if blocked_sigs:
            for b in blocked_sigs:
                events.append({
                    'type': 'blocked',
                    'direction': b.get('signal_type', 'long'),
                    'timestamp': to_ts(b.get('created_at')),
                    'price': float(b.get('entry_price', 0) or 0),
                    'rule_code': b.get('rule_code', '—'),
                    'blocked_reason': b.get('blocked_reason')
                })
    except Exception as e:
        import logging
        logging.error(f"Error querying trading_signals: {e}")

    for e in (entries or []):
        events.append({
            'type': 'entry',
            'direction': e['side'],
            'timestamp': to_ts(e.get('opened_at')),
            'price': float(e['entry_price'] or 0),
            'rule_code': e['rule_code'],
            'blocked_reason': None
        })
        
    for e in (exits or []):
        etype = 'tp_full'
        reason = (e.get('close_reason') or '').lower()
        if 'tp_partial' in reason: etype = 'tp_partial'
        elif 'sl' in reason: etype = 'sl'
        
        events.append({
            'type': etype,
            'direction': e['side'],
            'timestamp': to_ts(e.get('closed_at')),
            'price': float(e['exit_price'] or 0),
            'rule_code': e['rule_code'],
            'blocked_reason': None
        })
        
    return sorted(events, key=lambda x: x['timestamp'])


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
