from app.core.supabase_client import get_supabase
from app.core.logger import log_error, log_info

MODULE = "CENTINELA_ARBITRAGE"

def set_closing_in_progress(position_id: str, table: str = 'forex_positions') -> bool:
    """Sets closing_in_progress=True on the position in Supabase.
    Called BEFORE sending the close order.
    Returns True if successfully set.
    """
    try:
        sb = get_supabase()
        res = sb.table('centinela_position_state').update({'closing_in_progress': True}).eq('position_id', position_id).execute()
        return True
    except Exception as e:
        log_error(f"Error setting closing_in_progress for {position_id}: {str(e)}", MODULE)
        return False

def clear_closing_in_progress(position_id: str, table: str = 'forex_positions') -> bool:
    """Clears closing_in_progress flag. Called if close order fails."""
    try:
        sb = get_supabase()
        res = sb.table('centinela_position_state').update({'closing_in_progress': False}).eq('position_id', position_id).execute()
        return True
    except Exception as e:
        log_error(f"Error clearing closing_in_progress for {position_id}: {str(e)}", MODULE)
        return False

def check_closing_in_progress(position_id: str, table: str = 'forex_positions') -> bool:
    """Checks if closing_in_progress is set. Used by SLV/SLVM/Trailing to skip."""
    try:
        sb = get_supabase()
        res = sb.table('centinela_position_state').select('closing_in_progress').eq('position_id', position_id).execute()
        if res.data and len(res.data) > 0:
            return bool(res.data[0].get('closing_in_progress', False))
    except Exception as e:
        log_error(f"Error checking closing_in_progress for {position_id}: {str(e)}", MODULE)
    return False

def arbitrate_close_signal(decision: str, position: dict, state_tracker) -> dict:
    """Arbitrates CENTINELA close signal against existing module states.
    Returns: {'execute': bool, 'reason': str, 'blocked_by': str|None}
    """
    pos_id = position.get('id')
    
    # 1. Check if closing already in progress
    if position.get('closing_in_progress'):
        return {'execute': False, 'reason': 'Closing already in progress', 'blocked_by': 'System'}
        
    # 2. Check if EREP is active
    if position.get('erep_active'):
        return {'execute': False, 'reason': 'EREP is active', 'blocked_by': 'EREP'}
        
    # 3. Check if in recovery mode
    if position.get('recovery_mode'):
        return {'execute': False, 'reason': 'Recovery mode active', 'blocked_by': 'Recovery'}
        
    # 4. Check trailing stop overlap for partial closes
    if decision == 'CIERRE_PARCIAL' and position.get('trailing_stop_active'):
        return {'execute': False, 'reason': 'Trailing stop active during partial close', 'blocked_by': 'Trailing'}
        
    return {'execute': True, 'reason': 'Signal clear to execute', 'blocked_by': None}
