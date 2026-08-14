from enum import Enum
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from app.core.logger import log_info, log_error

MODULE = "CENTINELA_STATE_MACHINE"

class CentinelaState(Enum):
    NEUTRAL = 'neutral'
    VIGILANCIA = 'vigilancia'
    CIERRE_TOTAL = 'cierre_total'
    CIERRE_PARCIAL = 'cierre_parcial'
    MONITOREADO_POR_TRAILING = 'monitoreado_por_trailing'
    CERRADA = 'cerrada'

class PositionStateTracker:
    """In-memory state tracker for CENTINELA per-position states."""
    
    def __init__(self):
        self._states: Dict[str, dict] = {}
        
    def get_state(self, position_id: str) -> CentinelaState:
        state_info = self._states.get(position_id)
        if not state_info:
            return CentinelaState.NEUTRAL
        return state_info.get('state', CentinelaState.NEUTRAL)
        
    def transition(self, position_id: str, score_final: float, direction: str, squeeze_active: bool,
                   close_threshold: float, partial_range: Tuple[float, float]) -> CentinelaState:
        current_state = self.get_state(position_id)
        if current_state in (CentinelaState.CERRADA, CentinelaState.MONITOREADO_POR_TRAILING):
            return current_state
            
        is_long = direction.lower() == 'long'
        partial_low, partial_high = partial_range
        
        # Determine danger level based on direction
        in_danger = False
        danger_score = 0.0
        
        if is_long and score_final <= -25:
            in_danger = True
            danger_score = abs(score_final)
        elif not is_long and score_final >= 25:
            in_danger = True
            danger_score = score_final
            
        new_state = current_state
            
        if current_state == CentinelaState.NEUTRAL:
            if in_danger:
                new_state = CentinelaState.VIGILANCIA
                
        elif current_state == CentinelaState.VIGILANCIA:
            if not in_danger:
                new_state = CentinelaState.NEUTRAL
            elif danger_score >= close_threshold:
                new_state = CentinelaState.CIERRE_TOTAL
            elif partial_low <= danger_score < close_threshold and squeeze_active:
                new_state = CentinelaState.CIERRE_PARCIAL

        if new_state != current_state:
            log_info(f"Position {position_id} state transition: {current_state.value} -> {new_state.value}", MODULE)
            self._update_state(position_id, new_state)
            
        return new_state

    def is_in_cooldown(self, position_id: str, cooldown_seconds: int) -> bool:
        state_info = self._states.get(position_id)
        if not state_info or 'last_action_time' not in state_info:
            return False
            
        elapsed = (datetime.utcnow() - state_info['last_action_time']).total_seconds()
        return elapsed < cooldown_seconds

    def register_close_action(self, position_id: str, action_type: str):
        if action_type == 'CIERRE_TOTAL':
            self._update_state(position_id, CentinelaState.CERRADA)
        elif action_type == 'CIERRE_PARCIAL':
            self._update_state(position_id, CentinelaState.MONITOREADO_POR_TRAILING)
            
        if position_id in self._states:
            self._states[position_id]['last_action_time'] = datetime.utcnow()

    def cleanup_closed(self, active_position_ids: set):
        to_remove = []
        for pos_id in self._states.keys():
            if pos_id not in active_position_ids and self._states[pos_id].get('state') == CentinelaState.CERRADA:
                to_remove.append(pos_id)
                
        for pos_id in to_remove:
            del self._states[pos_id]
            
    def _update_state(self, position_id: str, new_state: CentinelaState):
        if position_id not in self._states:
            self._states[position_id] = {}
        self._states[position_id]['state'] = new_state
        self._states[position_id]['updated_at'] = datetime.utcnow()
        self.sync_to_db(position_id)

    def sync_to_db(self, position_id: str):
        # Sync state to centinela_position_state table if needed
        # This is a placeholder for DB operations
        pass

    def load_from_db(self, position_id: str):
        # Load from centinela_position_state table
        pass
