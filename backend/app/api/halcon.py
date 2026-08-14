from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional, Any
from datetime import datetime, timezone, timedelta
from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error

router = APIRouter(prefix='/api/halcon', tags=['halcon'])

class HalconConfigUpdate(BaseModel):
    """Model for updating HALCON parameters."""
    params: Dict[str, Any]

@router.get('/config')
def get_halcon_config():
    """Returns all HALCON CENTINELA configurable parameters."""
    try:
        sb = get_supabase()
        res = sb.table('system_config').select('*').like('key', 'halcon_%').execute()
        config = {}
        for item in (res.data or []):
            config[item['key']] = item['value']
        return {'config': config}
    except Exception as e:
        log_error(f"Error fetching HALCON config: {e}", "HALCON_API")
        return {'config': {}, 'error': str(e)}

@router.put('/config')
def update_halcon_config(update: HalconConfigUpdate):
    """Updates HALCON CENTINELA parameters in system_config."""
    sb = get_supabase()
    updated = []
    for key, value in update.params.items():
        if not key.startswith('halcon_'):
            key = f'halcon_{key}'
        try:
            sb.table('system_config').upsert({
                'key': key,
                'value': str(value)
            }).execute()
            updated.append(key)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error updating {key}: {e}")
    log_info(f"HALCON config updated: {updated}", 'HALCON_API')
    return {'updated': updated, 'count': len(updated)}

@router.get('/scores/recent')
def get_recent_scores(symbol: str = None, limit: int = 50):
    """Returns recent HALCON scores for monitoring."""
    try:
        sb = get_supabase()
        query = sb.table('halcon_scores_log').select('*').order('created_at', desc=True).limit(limit)
        if symbol:
            query = query.eq('symbol', symbol)
        res = query.execute()
        return {'scores': res.data or []}
    except Exception as e:
        return {'scores': [], 'error': str(e)}

@router.get('/decisions/recent')
def get_recent_decisions(symbol: str = None, limit: int = 50):
    """Returns recent CENTINELA decisions for monitoring."""
    try:
        sb = get_supabase()
        query = sb.table('centinela_decisions_log').select('*').order('created_at', desc=True).limit(limit)
        if symbol:
            query = query.eq('symbol', symbol)
        res = query.execute()
        return {'decisions': res.data or []}
    except Exception as e:
        return {'decisions': [], 'error': str(e)}

@router.get('/oraculo/events')
def get_oraculo_events(upcoming_only: bool = True):
    """Returns ORÁCULO economic calendar events."""
    try:
        sb = get_supabase()
        query = sb.table('oraculo_events').select('*').order('event_datetime', desc=False)
        if upcoming_only:
            now = datetime.now(timezone.utc).isoformat()
            query = query.gte('event_datetime', now)
        res = query.execute()
        return {'events': res.data or []}
    except Exception as e:
        return {'events': [], 'error': str(e)}

@router.get('/oraculo/paused')
def get_paused_symbols():
    """Returns currently paused symbols due to economic events."""
    try:
        from app.halcon_centinela.oraculo.pause_manager import OraculoPauseManager
        mgr = OraculoPauseManager()
        symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']
        paused = {}
        for s in symbols:
            result = mgr.check_trading_paused(s)
            if result.get('paused'):
                paused[s] = result
        return {'paused_symbols': paused}
    except Exception as e:
        return {'paused_symbols': {}, 'error': str(e)}

@router.get('/status')
def get_halcon_status():
    """Returns HALCON CENTINELA system status."""
    enabled = True
    decisions_count = 0
    try:
        sb = get_supabase()
        config = sb.table('system_config').select('value').eq('key', 'halcon_enabled').execute()
        if config.data:
            enabled = (config.data[0]['value'] == 'true')
        
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        decisions = sb.table('centinela_decisions_log').select('id', count='exact').gte('created_at', one_hour_ago).execute()
        if hasattr(decisions, 'count') and decisions.count is not None:
            decisions_count = decisions.count
    except Exception as e:
        pass
    
    return {
        'enabled': enabled,
        'decisions_last_hour': decisions_count,
    }
