from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.halcon_centinela.config import ORACULO_PARAMS, MODULE, CentinelaDecision
from app.halcon_centinela.logger import log_centinela_decision
from app.halcon_centinela.oraculo.calendar_service import EconomicCalendarService

class OraculoPauseManager:
    """Manages trading pauses before/after high-impact economic events."""
    
    def __init__(self, calendar_service: EconomicCalendarService = None,
                 params: dict = None):
        self.calendar = calendar_service or EconomicCalendarService()
        self.params = params or ORACULO_PARAMS
        self._pause_cache = {}  # symbol -> {paused, event, until}
    
    def check_trading_paused(self, symbol: str) -> dict:
        """Check if symbol is currently paused due to upcoming/recent event.
        Queries oraculo_events for events within pre/post window.
        Returns: {paused: bool, event_name: str, time_to_event: timedelta,
                  event_datetime: datetime, is_global: bool}
        FAIL-SAFE: If DB query fails, assume paused (conservative).
        """
        now = datetime.now(timezone.utc)
        pre_window = timedelta(minutes=self.params.get('pre_event_window_minutes', 60))
        post_window = timedelta(minutes=self.params.get('post_event_window_minutes', 60))
        
        try:
            supabase = get_supabase()
            start_time = (now - post_window).isoformat()
            end_time = (now + pre_window).isoformat()
            
            response = supabase.table('oraculo_events')\
                .select('*')\
                .filter('event_datetime', 'gte', start_time)\
                .filter('event_datetime', 'lte', end_time)\
                .execute()
                
            events = response.data
            for ev in events:
                affected_symbols = ev.get('affected_symbols', [])
                if ev.get('is_global') or symbol in affected_symbols:
                    event_dt = datetime.fromisoformat(ev['event_datetime'].replace('Z', '+00:00'))
                    
                    if now < event_dt:
                        time_to_event = event_dt - now
                    else:
                        time_to_event = timedelta(0)
                        
                    return {
                        'paused': True,
                        'event_name': ev.get('event_name'),
                        'time_to_event': time_to_event,
                        'event_datetime': event_dt,
                        'is_global': ev.get('is_global', False)
                    }
            
            return {
                'paused': False,
                'event_name': None,
                'time_to_event': timedelta(0),
                'event_datetime': None,
                'is_global': False
            }
            
        except Exception as e:
            log_error(f"Error querying oraculo_events: {e}. Assuming paused for safety.", MODULE)
            return {
                'paused': True,
                'event_name': 'UNKNOWN_ERROR',
                'time_to_event': timedelta(0),
                'event_datetime': now,
                'is_global': True
            }
    
    def evaluate_pause_actions(self, symbol: str, positions: list,
                               execution_service=None) -> list:
        """For each open position on a paused symbol:
        - PNL > -$5 → execute CIERRE_TOTAL immediately (bypass HALCON score)
        - PNL <= -$5 → place bracket SL/TP via BracketManager
        Returns list of actions taken.
        """
        actions_taken = []
        threshold = self.params.get('market_close_pnl_threshold', -5.0)
        
        for pos in positions:
            pnl = float(pos.get('unrealized_pnl', 0.0))
            pos_id = pos.get('id', 'unknown')
            
            if pnl > threshold:
                executed = False
                result = {}
                if execution_service:
                    try:
                        result = execution_service.close_position(pos_id, symbol)
                        executed = True
                    except Exception as e:
                        log_error(f"Error closing pos {pos_id} on {symbol}: {e}", MODULE)
                        result = {'error': str(e)}
                
                log_centinela_decision(
                    position_id=pos_id,
                    symbol=symbol,
                    decision=CentinelaDecision.CIERRE_TOTAL,
                    reason="ORACULO_PAUSE",
                    score_final=0.0,
                    pnl_at_decision=pnl,
                    oraculo_override=True,
                    executed=executed,
                    execution_result=result
                )
                actions_taken.append({
                    'position_id': pos_id,
                    'action': 'CIERRE_TOTAL',
                    'executed': executed
                })
            else:
                executed = False
                result = {}
                if execution_service and hasattr(execution_service, 'bracket_manager'):
                    try:
                        squeeze_active = pos.get('squeeze_active', False)
                        market_type = 'crypto' if 'USDT' in symbol or symbol.startswith('BTC') else 'forex'
                        result = execution_service.bracket_manager.place_bracket(pos, squeeze_active, market_type)
                        executed = result.get('bracket_placed', False)
                    except Exception as e:
                        log_error(f"Error placing bracket for {pos_id}: {e}", MODULE)
                        result = {'error': str(e)}
                
                log_centinela_decision(
                    position_id=pos_id,
                    symbol=symbol,
                    decision=CentinelaDecision.MANTENER,
                    reason="ORACULO_BRACKET",
                    score_final=0.0,
                    pnl_at_decision=pnl,
                    oraculo_override=True,
                    executed=executed,
                    execution_result=result
                )
                actions_taken.append({
                    'position_id': pos_id,
                    'action': 'PLACE_BRACKET',
                    'executed': executed
                })
                
        return actions_taken
    
    def release_pause(self, symbol: str):
        """Release pause after post-event window expires.
        Cancel any brackets that weren't triggered.
        """
        if symbol in self._pause_cache:
            del self._pause_cache[symbol]
            log_info(f"Released trading pause for {symbol}", MODULE)
    
    def refresh_pauses(self):
        """Called periodically (every 60min or after calendar sync).
        Updates _pause_cache for all active symbols.
        """
        pass
