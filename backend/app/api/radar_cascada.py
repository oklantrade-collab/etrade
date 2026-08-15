"""
API Endpoints for RADAR, CASCADA and Unified Strategy HUD.
eTrade v5.0
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta

from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error
from app.radar.radar_service import RadarService
from app.cascada.cascada_manager import CascadaManager

router = APIRouter(prefix='/api/v1/strategy-hub', tags=['RADAR & CASCADA Hub'])


@router.get('/radar/snapshot')
def get_radar_snapshot(symbol: Optional[str] = Query(None, description="Symbol to fetch (e.g. EURUSD, BTCUSDT)")):
    """
    Returns the real-time RADAR signal snapshot.
    If symbol is provided, returns single snapshot; otherwise returns all monitored symbols.
    """
    radar = RadarService.get_instance()
    if symbol:
        snap = radar.get_snapshot(symbol)
        return {'symbol': symbol.upper(), 'snapshot': snap}
    
    # If no symbol provided, gather for default monitored pairs
    default_symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    snapshots = {s: radar.get_snapshot(s) for s in default_symbols}
    return {'snapshots': snapshots}


@router.get('/radar/events')
def get_radar_events(
    symbol: str = Query(..., description="Symbol to fetch events for"),
    event_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Returns recent discrete events from RADAR event bus.
    """
    radar = RadarService.get_instance()
    events = radar.get_events_for_symbol(symbol, event_type=event_type, limit=limit)
    return {'symbol': symbol.upper(), 'events': events}


@router.get('/cascada/positions')
def get_cascada_positions(market_type: str = Query('all', description="'forex', 'crypto', or 'all'")):
    """
    Returns all currently open positions with CASCADA state (cascade_level, cascade_hold, pnl_pico).
    """
    try:
        sb = get_supabase()
        positions = []

        if market_type in ('forex', 'all'):
            f_res = sb.table('forex_positions').select('*').eq('status', 'open').execute()
            for p in (f_res.data or []):
                p['market_type'] = 'forex'
                positions.append(p)

        if market_type in ('crypto', 'all'):
            c_res = sb.table('positions').select('*').eq('status', 'open').execute()
            for p in (c_res.data or []):
                p['market_type'] = 'crypto'
                positions.append(p)

        return {'positions': positions}
    except Exception as e:
        log_error(f"Error fetching cascada positions: {e}", "CASCADA_API")
        return {'positions': [], 'error': str(e)}


@router.get('/cascada/decisions/recent')
def get_recent_cascada_decisions(symbol: Optional[str] = None, limit: int = 50):
    """
    Returns recent CASCADA decisions from DB log.
    """
    try:
        sb = get_supabase()
        query = sb.table('cascada_decisions_log').select('*').order('created_at', desc=True).limit(limit)
        if symbol:
            query = query.eq('symbol', symbol.upper())
        res = query.execute()
        return {'decisions': res.data or []}
    except Exception as e:
        log_error(f"Error fetching cascada decisions: {e}", "CASCADA_API")
        return {'decisions': [], 'error': str(e)}


@router.get('/hud/{symbol}')
def get_symbol_strategy_hud(symbol: str):
    """
    Aggregates full strategic status for a symbol combining:
    - RADAR: Slopes, ADX, Local Regime, Fibonacci Zone, Squeeze, Volume
    - CASCADA: Active cascade level, cascade_hold, giveback floor
    - HALCÓN: Macro score, Oráculo status
    """
    sym = symbol.upper()
    radar = RadarService.get_instance()
    radar_snap = radar.get_snapshot(sym)

    # Check for active position in Forex or Crypto
    sb = get_supabase()
    pos_data = None
    try:
        # Check forex
        f_res = sb.table('forex_positions').select('*').eq('symbol', sym).eq('status', 'open').limit(1).execute()
        if f_res.data:
            pos_data = f_res.data[0]
            pos_data['market_type'] = 'forex'
        else:
            # Check crypto
            c_res = sb.table('positions').select('*').eq('symbol', sym).eq('status', 'open').limit(1).execute()
            if c_res.data:
                pos_data = c_res.data[0]
                pos_data['market_type'] = 'crypto'
    except Exception:
        pos_data = None

    # Gather Halcon recent score or compute on the fly
    halcon_score = 0.0
    halcon_semaforo = 'VERDE'
    try:
        h_res = sb.table('halcon_scores_log').select('score_final, semaforo').eq('symbol', sym).order('created_at', desc=True).limit(1).execute()
        if h_res.data:
            halcon_score = float(h_res.data[0].get('score_final', 0.0))
            halcon_semaforo = str(h_res.data[0].get('semaforo', 'VERDE'))
        else:
            # Fallback estimation from RADAR indicators
            adx = float(radar_snap.get('adx_val', 20.0))
            rsi = float(radar_snap.get('rsi_val', 50.0))
            squeeze = bool(radar_snap.get('squeeze_activo', False))
            
            calc_score = 0.0
            if rsi >= 75 or rsi <= 25: calc_score += 30.0
            if squeeze: calc_score += 20.0
            if adx < 15.0: calc_score += 15.0
            
            halcon_score = calc_score
            if halcon_score >= 60.0:
                halcon_semaforo = 'ROJO'
            elif halcon_score >= 35.0:
                halcon_semaforo = 'AMARILLO'
            else:
                halcon_semaforo = 'VERDE'
    except Exception:
        halcon_score = 15.0
        halcon_semaforo = 'VERDE'

    # Compute Cascada projected level from EMA alignment & Fibonacci zone
    projected_level = 0
    fib_zone = abs(int(radar_snap.get('fibonacci_zone', 0)))
    slope_ema3 = radar_snap.get('pendiente_EMA3', '')
    slope_ema9 = radar_snap.get('pendiente_EMA9', '')
    slope_ema20 = radar_snap.get('pendiente_EMA20', '')
    local_regime = radar_snap.get('regimen_local_15m', '')

    if fib_zone >= 5:
        projected_level = 5
    elif local_regime in ('bullish', 'bearish') and slope_ema20 in ('ascending', 'descending'):
        projected_level = 4
    elif (slope_ema3 == slope_ema9 == slope_ema20) and slope_ema3 in ('ascending', 'descending'):
        projected_level = 3
    elif slope_ema3 == slope_ema9 and slope_ema3 in ('ascending', 'descending'):
        projected_level = 2
    elif slope_ema3 in ('ascending', 'descending'):
        projected_level = 1
    else:
        projected_level = 0

    # If no open position, fetch last closed position for historical context
    last_closed_pos = None
    if not pos_data:
        try:
            lc_f = sb.table('forex_positions').select('*').eq('symbol', sym).eq('status', 'closed').order('closed_at', desc=True).limit(1).execute()
            if lc_f.data:
                last_closed_pos = lc_f.data[0]
            else:
                lc_c = sb.table('positions').select('*').eq('symbol', sym).eq('status', 'closed').order('closed_at', desc=True).limit(1).execute()
                if lc_c.data:
                    last_closed_pos = lc_c.data[0]
        except Exception:
            pass

    return {
        'symbol': sym,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'radar': radar_snap,
        'cascada': {
            'projected_level': projected_level,
            'current_level': pos_data.get('cascade_level', projected_level) if pos_data else projected_level,
            'cascade_hold': bool(pos_data.get('cascade_hold', False)) if pos_data else False,
            'pnl_pico': float(pos_data.get('pnl_pico', 0.0)) if pos_data else float(last_closed_pos.get('pnl_pico', 0.0) if last_closed_pos else 0.0),
            'last_closed_position': last_closed_pos
        },
        'halcon': {
            'score_final': halcon_score,
            'semaforo': halcon_semaforo,
            'trading_paused': radar_snap.get('trading_paused', False)
        },
        'position': pos_data or last_closed_pos
    }
