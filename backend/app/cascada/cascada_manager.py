"""
CASCADA Position Manager Orchestrator.
eTrade v5.0 — Spec Section 3 & 4
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from app.core.logger import log_info, log_error, log_warning
from app.core.supabase_client import get_supabase
from app.core.memory_store import get_memory_df
from app.radar.radar_service import RadarService
from app.cascada.config import MODULE, CASCADA_PARAMS, load_cascada_config_from_db
from app.cascada.cascada_engine import CascadaEngine, CascadaResult
from app.cascada.logger import log_cascada_decision


class CascadaManager:
    """
    Orchestrates the evaluation of open REBOTE positions across CASCADA levels,
    persisting state updates to DB and directing closing actions.
    """
    _instance = None

    def __init__(self, radar_service: Optional[RadarService] = None, params: Optional[Dict[str, Any]] = None):
        self.params = params or load_cascada_config_from_db()
        self.radar = radar_service or RadarService.get_instance()
        self.engine = CascadaEngine(self.params)
        self.sb = get_supabase()

    @classmethod
    def get_instance(cls) -> 'CascadaManager':
        if cls._instance is None:
            cls._instance = CascadaManager()
        return cls._instance

    def evaluate_all_cascade_positions(
        self, 
        open_positions: List[Dict[str, Any]], 
        market_type: str = 'forex'
    ) -> List[CascadaResult]:
        """
        Filters positions with origen='REBOTE' and evaluates each under CASCADA.
        Updates DB columns (cascade_level, cascade_hold, pnl_pico) and returns results list.
        """
        results = []
        if not open_positions or not self.params.get('enabled', True):
            return results

        # Filter only REBOTE positions
        cascade_candidates = [
            p for p in open_positions 
            if str(p.get('origen', '')).upper() == 'REBOTE' or str(p.get('rule_code', '')).startswith(('AaReb', 'BbReb', 'REBOTE'))
        ]

        if not cascade_candidates:
            return results

        for pos in cascade_candidates:
            try:
                sym = str(pos.get('symbol', '')).upper()
                pos_id = str(pos.get('id', ''))

                # Gather RADAR data
                snapshot = self.radar.get_snapshot(sym)
                events = self.radar.get_events_for_symbol(sym, limit=20)

                # Gather DataFrames
                df_15m = get_memory_df(sym, '15m')
                df_1h = get_memory_df(sym, '1h')

                # Evaluate
                pos['market_type'] = market_type
                result = self.engine.evaluate(pos, snapshot, events, df_15m, df_1h)
                results.append(result)

                # Log decision
                log_cascada_decision(result)

                # Update position state in DB
                self._update_position_db_state(pos_id, result, market_type)

            except Exception as e:
                log_error(MODULE, f"Error evaluating CASCADA for pos {pos.get('id')}: {e}")

        return results

    def should_delegate_slv(self, position: Dict[str, Any]) -> bool:
        """
        Spec Section 3.6:
        Determines whether SLV/SLVM should delegate its EMA3<EMA9 closing trigger
        to CASCADA. True if position origin is REBOTE.
        """
        origen = str(position.get('origen', '')).upper()
        rule_code = str(position.get('rule_code', ''))
        return origen == 'REBOTE' or rule_code.startswith(('AaReb', 'BbReb', 'REBOTE'))

    def _update_position_db_state(self, pos_id: str, result: CascadaResult, market_type: str) -> None:
        """
        Persists updated cascade_level, cascade_hold, and pnl_pico to the respective positions table.
        """
        table_name = 'forex_positions' if market_type == 'forex' else 'positions'
        try:
            update_data = {
                'cascade_level': result.current_level,
                'cascade_hold': result.cascade_hold,
                'pnl_pico': result.pnl_pico
            }
            self.sb.table(table_name).update(update_data).eq('id', pos_id).execute()
        except Exception as e:
            log_error(MODULE, f"Error updating position DB state ({table_name} id={pos_id}): {e}")
