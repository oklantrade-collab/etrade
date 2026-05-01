from fastapi import APIRouter, Depends
import os
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from app.core.supabase_client import get_supabase

router = APIRouter()

def calculate_forex_indicators(candles):
    if not candles: return []
    try:
        df = pd.DataFrame(candles)
        # Ensure numeric and sort chronologically
        for col in ['open','high','low','close']: 
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Calculate EMA20 (Standard for our Forex model)
        df['basis'] = df['close'].ewm(span=20, adjust=False).mean()
        
        # Calculate ATR14
        df['tr'] = np.maximum(df['high'] - df['low'], 
                             np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                        abs(df['low'] - df['close'].shift(1))))
        df['atr'] = df['tr'].rolling(window=14).mean()
        
        # Fill ATR gaps at start with SMA of TR
        df.loc[df.index[:14], 'atr'] = df['tr'].rolling(window=14, min_periods=1).mean()

        multipliers = [1.618, 2.618, 3.618, 4.236, 5.618, 6.618]
        for i, m in enumerate(multipliers, 1):
            df[f'upper_{i}'] = df['basis'] + (df['atr'] * m)
            df[f'lower_{i}'] = df['basis'] - (df['atr'] * m)
        
        # SAR calculation fallback
        from app.analysis.parabolic_sar import calculate_parabolic_sar
        calculate_parabolic_sar(df)

        return df.fillna(0).to_dict('records')
    except Exception as e:
        print(f"Error calculating API indicators: {e}")
        return candles

@router.get('/status')
async def get_forex_status(
    sb = Depends(get_supabase)
):
    """Verificar si Forex está configurado y conectado."""
    try:
        has_credentials = all([
            os.getenv('CTRADER_CLIENT_ID'),
            os.getenv('CTRADER_CLIENT_SECRET'),
            os.getenv('CTRADER_ACCOUNT_ID'),
            os.getenv('CTRADER_ACCESS_TOKEN'),
        ])
        config_res = sb.table('trading_config').select('capital_forex_futures, regime_params').eq('id', 1).execute()
        config = config_res.data[0] if config_res.data else {}
        has_capital = float(config.get('capital_forex_futures', 0) or 0) > 0
        connected = has_credentials and has_capital
        return {
            'connected': connected,
            'has_credentials': has_credentials,
            'has_capital': has_capital,
            'environment': os.getenv('CTRADER_ENV', 'demo'),
            'pairs_configured': (config.get('regime_params', {}) or {}).get('forex_assets', ['EURUSD','GBPUSD','USDJPY','XAUUSD']) if connected else [],
        }
    except Exception as e:
        return {'connected': False, 'error': str(e)}

@router.get('/snapshots')
async def get_forex_snapshots(
    sb = Depends(get_supabase)
):
    """Obtener snapshots de pares Forex."""
    try:
        config_res = sb.table('trading_config').select('regime_params').eq('id', 1).execute()
        config = config_res.data[0] if config_res.data else {}
        pairs = (config.get('regime_params', {}) or {}).get('forex_assets', ['EURUSD','GBPUSD','USDJPY','XAUUSD'])
        res = sb.table('market_snapshot').select('*').in_('symbol', pairs).execute()
        return { row['symbol']: row for row in (res.data or []) }
    except Exception as e:
        return {}

@router.get('/candles')
async def get_forex_candles(
    symbol: str = 'EURUSD',
    timeframe: str = '15m',
    sb = Depends(get_supabase)
):
    """Obtener velas históricas con indicadores técnicos."""
    try:
        res = sb.table('market_candles')\
            .select('*')\
            .eq('symbol', symbol)\
            .eq('timeframe', timeframe)\
            .eq('exchange', 'icmarkets')\
            .order('open_time', desc=True)\
            .limit(300)\
            .execute()
        candles = res.data or []
        candles.reverse()
        full_candles = calculate_forex_indicators(candles)
        return full_candles
    except Exception as e:
        print(f"Candles API Error: {e}")
        return []
    
@router.get('/positions')
async def get_forex_positions(
    status: str = 'open',
    sb = Depends(get_supabase)
):
    """Obtener posiciones de Forex (abiertas o cerradas)."""
    try:
        res = sb.table('forex_positions')\
            .select('*')\
            .eq('status', status)\
            .order('opened_at', desc=True)\
            .execute()
        return res.data or []
    except Exception as e:
        return []

@router.get('/dashboard/summary')
async def get_forex_dashboard(
    sb = Depends(get_supabase)
):
    """
    Retorna todos los datos del dashboard
    desde Supabase (lectura local, sin cTrader).
    Tiempo de respuesta: < 50ms
    """
    # Snapshots actuales
    snaps_res = sb.table('market_snapshot')\
        .select('*')\
        .in_('symbol', [
            'EURUSD','GBPUSD',
            'USDJPY','XAUUSD'
        ])\
        .execute()
    snapshots = {
        s['symbol']: s
        for s in (snaps_res.data or [])
    }

    # Posiciones abiertas
    pos_res = sb.table('forex_positions')\
        .select('*')\
        .eq('status', 'open')\
        .execute()
    positions = pos_res.data or []

    # P&L del día
    today = datetime.now(timezone.utc)\
        .replace(hour=0, minute=0, second=0)\
        .isoformat()
    pnl_res = sb.table('forex_positions')\
        .select('realized_pnl,symbol')\
        .gte('closed_at', today)\
        .eq('status', 'closed')\
        .execute()
    daily_pnl = sum(
        float(r.get('realized_pnl', 0) or 0)
        for r in (pnl_res.data or [])
    )

    return {
        'snapshots':      snapshots,
        'positions':      positions,
        'daily_pnl':      round(daily_pnl, 2),
        'timestamp':      datetime.now(
            timezone.utc
        ).isoformat(),
    }

@router.get('/dashboard/positions')
async def get_positions_live_forex(
    sb = Depends(get_supabase)
):
    """
    Posiciones con P&L calculado desde Supabase.
    """
    pos_res = sb.table('forex_positions')\
        .select('*')\
        .eq('status', 'open')\
        .order('opened_at', desc=True)\
        .execute()
    positions = pos_res.data or []

    # Enriquecer con precio actual
    snaps_res = sb.table('market_snapshot')\
        .select('symbol,price,fibonacci_zone')\
        .execute()
    price_map = {
        s['symbol']: s
        for s in (snaps_res.data or [])
    }

    from app.strategy.forex_adaptive_exit import _pip_size

    for pos in positions:
        symbol = pos.get('symbol', '')
        snap   = price_map.get(symbol, {})
        price  = float(snap.get('price', 0))
        entry  = float(pos.get(
            'avg_entry_price', 0
        ) or pos.get('entry_price', 0) or 0)
        side   = str(pos.get('side', 'long'))

        if price > 0 and entry > 0:
            pip = _pip_size(symbol)
            if side in ('long', 'buy'):
                pnl_pips = (price - entry) / pip
            else:
                pnl_pips = (entry - price) / pip
            
            pnl_pct = pnl_pips * pip / entry * 100 if entry > 0 else 0

            pos['current_price'] = price
            pos['unrealized_pnl_pct'] = round(pnl_pct, 4)
            pos['unrealized_pnl_pips'] = round(pnl_pips, 1)
            pos['fib_zone'] = snap.get(
                'fibonacci_zone', 0
            )

    return {
        'positions':  positions,
        'count':      len(positions),
        'timestamp':  datetime.now(
            timezone.utc
        ).isoformat(),
    }
