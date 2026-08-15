from typing import List, Dict, Any
from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error, log_warning
from app.core.memory_store import MEMORY_STORE, get_memory_df

from app.halcon_centinela.halcon_engine import HalconEngine, HalconResult
from app.halcon_centinela.state_machine import PositionStateTracker, CentinelaState
from app.halcon_centinela.arbitrage import arbitrate_close_signal, set_closing_in_progress, clear_closing_in_progress
from app.halcon_centinela.config import CentinelaDecision
from app.halcon_centinela.logger import log_halcon_score, log_centinela_decision

MODULE = "CENTINELA_MONITOR"

class CentinelaMonitor:
    """CENTINELA: Proactive close executor running over all open positions."""
    
    def __init__(self, execution_service=None, supabase=None, 
                 halcon_engine: HalconEngine = None,
                 state_tracker: PositionStateTracker = None,
                 oraculo_manager=None,
                 market_type: str = 'forex'):
        self.execution_service = execution_service
        self.sb = supabase or get_supabase()
        self.halcon = halcon_engine or HalconEngine()
        self.state_tracker = state_tracker or PositionStateTracker()
        self.oraculo = oraculo_manager
        self.market_type = market_type
        
    def evaluate_all_positions(self, open_positions: List[dict]) -> List[dict]:
        """Main entry point. Iterates all open positions and evaluates each."""
        results = []
        
        if not open_positions:
            return results
            
        active_ids = {str(p.get('id')) for p in open_positions if p.get('id')}
        self.state_tracker.cleanup_closed(active_ids)
        
        for pos in open_positions:
            try:
                curr_pnl = pos.get('current_pnl')
                if curr_pnl is None or curr_pnl == 0:
                    for key in ['unrealized_pnl', 'unrealized_pnl_usd']:
                        val = pos.get(key)
                        if val is not None and val != 0:
                            pos['current_pnl'] = val
                            break
                
                curr_price = pos.get('current_price')
                if curr_price is None or curr_price == 0:
                    for key in ['mark_price', 'current_price_usd', 'price']:
                        val = pos.get(key)
                        if val is not None and val != 0:
                            pos['current_price'] = val
                            break

                res = self._evaluate_single_position(pos)
                if res:
                    results.append(res)
            except Exception as e:
                log_error(f"Failed to evaluate position {pos.get('id')}: {str(e)}", MODULE)
                
        return results

    def _evaluate_single_position(self, position: dict) -> dict:
        norm_pos = self._normalize_position(position)
        pos_id = str(norm_pos.get('id'))
        
        # 1. Check cooldown
        cooldown = self.halcon.params.get('cooldown_seconds', 300)
        if self.state_tracker.is_in_cooldown(pos_id, cooldown):
            return {'position_id': pos_id, 'decision': 'COOLDOWN', 'executed': False}
            
        # 2. Check ORACULO pause
        if self.oraculo and self.oraculo.check_trading_paused(norm_pos.get('symbol')).get('paused', False):
            return {'position_id': pos_id, 'decision': 'ORACULO_PAUSE', 'executed': False}

        # 3. Gather market data
        symbol = norm_pos.get('symbol')
        market_data = self._gather_market_data(symbol)
        
        # 4. Call halcon engine
        halcon_result = self.halcon.evaluate(norm_pos, market_data)
        
        # Log score
        class _EWrap:
            def __init__(self, v): self.value = v
        log_halcon_score(
            position_id=pos_id,
            symbol=symbol,
            scores_by_layer=getattr(halcon_result, 'scores_by_layer', {}),
            score_final=halcon_result.score_final,
            semaforo=_EWrap(halcon_result.semaforo) if isinstance(halcon_result.semaforo, str) else halcon_result.semaforo,
            decision=_EWrap(halcon_result.decision) if isinstance(halcon_result.decision, str) else halcon_result.decision,
            executed=False,
            detail=halcon_result.detail
        )

        # 5. Apply state machine transition
        partial_range = (self.halcon.params.get('threshold_cierre_parcial_low', 25.0),
                         self.halcon.params.get('threshold_cierre_parcial_high', 60.0))
                         
        new_state = self.state_tracker.transition(
            pos_id, 
            halcon_result.score_final, 
            norm_pos.get('direction', 'long'),
            halcon_result.squeeze_active,
            self.halcon.params.get('threshold_cierre_total', 60.0),
            partial_range
        )
        
        decision = halcon_result.decision
        executed = False
        
        # 6. Arbitrate if decision is to close
        if decision in (CentinelaDecision.CIERRE_TOTAL.value, CentinelaDecision.CIERRE_PARCIAL.value):
            # Spec 4.1.2: Check cascade_hold lock
            if norm_pos.get('cascade_hold', False):
                decision = "BLOCKED_BY_CASCADE_HOLD"
                log_info(f"[{MODULE}] Position {pos_id} close blocked by active CASCADE_HOLD", MODULE)
            else:
                arbitration = arbitrate_close_signal(decision, norm_pos, self.state_tracker)
                if arbitration['execute']:
                    # 7. Execute close
                    executed = self._execute_close(norm_pos, decision, halcon_result)
                    if executed:
                        self.state_tracker.register_close_action(pos_id, decision)
                else:
                    decision = f"BLOCKED_BY_{arbitration['blocked_by']}"

        # 8. Log decision
        class _DWrap:
            def __init__(self, v): self.value = v
        log_centinela_decision(
            position_id=pos_id,
            symbol=symbol,
            decision=_DWrap(decision) if isinstance(decision, str) else decision,
            reason="HALCON_EVALUATION" if not str(decision).startswith("BLOCKED") else f"Arbitration: {decision}",
            score_final=halcon_result.score_final,
            pnl_at_decision=norm_pos.get('current_pnl', 0.0),
            oraculo_override=False,
            executed=executed
        )
        
        return {
            'position_id': pos_id,
            'decision': decision,
            'score_final': halcon_result.score_final,
            'executed': executed,
            'detail': halcon_result.detail
        }

    def _gather_market_data(self, symbol: str) -> dict:
        data = {
            'df_1d': get_memory_df(symbol, '1d'),
            'df_4h': get_memory_df(symbol, '4h'),
            'df_15m': get_memory_df(symbol, '15m'),
            'df_5m': get_memory_df(symbol, '5m'),
            'df_1m': get_memory_df(symbol, '1m'),
            'snapshot': MEMORY_STORE.get('snapshots', {}).get(symbol, {})
        }
        for tf, df in data.items():
            if tf.startswith('df_') and df is not None and not df.empty:
                if 'ema1' in df.columns and 'ema_3' not in df.columns:
                    df['ema_3'] = df['ema1']
                if 'ema2' in df.columns and 'ema_9' not in df.columns:
                    df['ema_9'] = df['ema2']
                if 'ema3' in df.columns and 'ema_20' not in df.columns:
                    df['ema_20'] = df['ema3']
                if 'rsi_14' in df.columns and 'rsi' not in df.columns:
                    df['rsi'] = df['rsi_14']
        return data

    def _execute_close(self, position: dict, decision: str, halcon_result: HalconResult) -> bool:
        if not self.execution_service:
            log_warning("No execution service configured for CentinelaMonitor", MODULE)
            return False
            
        pos_id = str(position.get('id'))
        table = 'forex_positions' if self.market_type == 'forex' else 'positions'
        
        if not set_closing_in_progress(pos_id, table):
            return False
            
        try:
            current_price = position.get('current_price', 0.0)
            reason = f"CENTINELA {decision} (Score: {halcon_result.score_final})"
            
            if self.market_type == 'forex':
                pips_pnl = position.get('pips_pnl', 0.0)
                if decision == CentinelaDecision.CIERRE_TOTAL.value:
                    self.execution_service._close_position(position, current_price, reason, pips_pnl)
                elif decision == CentinelaDecision.CIERRE_PARCIAL.value:
                    self.execution_service._partial_close_position(position, current_price, 0.5, pips_pnl)
            else:
                # Crypto
                if decision == CentinelaDecision.CIERRE_TOTAL.value:
                    self.execution_service.close_position(pos_id, reason)
                elif decision == CentinelaDecision.CIERRE_PARCIAL.value:
                    # Implement partial close for crypto if execution service supports it
                    log_warning(f"Crypto partial close not natively supported yet for {pos_id}", MODULE)
                    self.execution_service.close_position(pos_id, reason + " (Partial request converted to total)")
                    
            return True
        except Exception as e:
            log_error(f"Error executing close for {pos_id}: {str(e)}", MODULE)
            clear_closing_in_progress(pos_id, table)
            return False

    def _normalize_position(self, position: dict) -> dict:
        norm = position.copy()
        
        # Side mapping
        if 'side' in norm and 'direction' not in norm:
            norm['direction'] = norm['side']
            
        # PnL mapping
        norm['current_pnl'] = self._get_current_pnl(norm)
            
        # Size mapping
        if 'size' in norm:
            norm['position_size'] = norm['size']
        elif 'lots' in norm:
            norm['position_size'] = norm['lots']
            
        return norm

    def _get_current_pnl(self, position: dict) -> float:
        for key in ['current_pnl', 'pnl_usd', 'unrealized_pnl']:
            if key in position:
                try:
                    return float(position[key])
                except (ValueError, TypeError):
                    continue
        return 0.0
