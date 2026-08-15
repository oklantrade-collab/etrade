from typing import List, Dict, Any, Optional
from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error, log_warning
from app.core.memory_store import MEMORY_STORE, get_memory_df, BOT_STATE

from app.rebote_aduana.rebote_engine import ReboteEngine, ReboteResult
from app.rebote_aduana.aduana_validator import AduanaValidator, AduanaResult
from app.rebote_aduana.config import REBOTE_PARAMS, ADUANA_PARAMS, MODULE
from app.rebote_aduana.logger import log_rebote_score, log_aduana_decision

class ReboteMonitor:
    """Async monitor that scans symbols for REBOTE entry opportunities."""

    def __init__(self, execution_service=None, supabase=None,
                 rebote_engine: ReboteEngine = None,
                 aduana_validator: AduanaValidator = None,
                 oraculo_manager=None,
                 market_type: str = 'forex'):
        self.execution_service = execution_service
        self.sb = supabase or get_supabase()
        self.engine = rebote_engine or ReboteEngine()
        self.aduana = aduana_validator or AduanaValidator(oraculo_manager=oraculo_manager)
        self.oraculo = oraculo_manager
        self.market_type = market_type

    def scan_all_symbols(self, symbols: List[str]) -> List[dict]:
        """Scan all symbols for REBOTE entry opportunities.
        Called periodically from the worker scheduler loop.
        Returns list of results (entries made, skipped, rejected by ADUANA).
        """
        results = []
        if not symbols:
            return results

        for symbol in symbols:
            try:
                market_data = self._gather_market_data(symbol)
                for direction in ('long', 'short'):
                    res = self._evaluate_symbol_direction(symbol, direction, market_data)
                    if res:
                        results.append(res)
            except Exception as e:
                log_error(MODULE, f"Failed to scan symbol {symbol}: {str(e)}")
        
        return results

    def _evaluate_symbol_direction(self, symbol: str, direction: str, market_data: dict) -> dict:
        """Evaluate a single symbol and direction for a potential REBOTE entry."""
        # 1. Count existing open positions for this symbol+direction
        existing_count = self._count_open_positions(symbol, direction)
        
        # 2. Get max_positions
        max_positions = BOT_STATE.config_cache.get('max_positions_per_symbol', 4)
        
        # 3. If existing >= max_positions → skip
        if existing_count >= max_positions:
            return {
                'symbol': symbol, 'direction': direction, 'decision': 'SKIP', 
                'reason': f'Max positions reached ({existing_count}/{max_positions})'
            }
            
        # 4. Determine score threshold
        threshold = float(BOT_STATE.config_cache.get(
            'rebote_score_min_additional' if existing_count > 0 else 'rebote_score_min_entry', 
            70.0 if existing_count > 0 else 50.0
        ))
        
        # 5. Call engine.evaluate
        result = self.engine.evaluate(symbol, direction, market_data)
        
        # 6. Log the evaluation
        log_rebote_score(symbol, result)
        
        # 7. Check threshold and decision
        if result.score_final < threshold or result.decision != 'ENTER':
            return {
                'symbol': symbol, 'direction': direction, 'decision': 'SKIP',
                'reason': f"Score {result.score_final} < {threshold} or not ENTER",
                'score_final': result.score_final
            }
            
        # 8. Call aduana validate
        aduana_res = self.aduana.validate(
            symbol=symbol,
            side=direction,
            order_type='LIMIT',
            market_data=market_data,
            strategy='REBOTE',
            contra_trend_confirmed=result.contra_trend_confirmed
        )
        
        # 9. Log ADUANA decision
        log_aduana_decision(symbol, direction, 'LIMIT', aduana_res, strategy='REBOTE')
        
        # 10. Check ADUANA approval
        if not aduana_res.approved:
            return {
                'symbol': symbol, 'direction': direction, 'decision': 'REJECTED_BY_ADUANA',
                'reason': aduana_res.reason,
                'score_final': result.score_final
            }
            
        # 11. Execute entry
        executed = self._execute_entry(symbol, direction, result)
        
        return {
            'symbol': symbol,
            'direction': direction,
            'decision': 'ENTERED' if executed else 'EXECUTION_FAILED',
            'score_final': result.score_final,
            'executed': executed
        }

    def _gather_market_data(self, symbol: str) -> dict:
        return {
            'df_1d': get_memory_df(symbol, '1d'),
            'df_4h': get_memory_df(symbol, '4h'),
            'df_15m': get_memory_df(symbol, '15m'),
            'df_5m': get_memory_df(symbol, '5m'),
            'df_1m': get_memory_df(symbol, '1m'),
            'snapshot': MEMORY_STORE.get('snapshots', {}).get(symbol, {})
        }

    def _count_open_positions(self, symbol: str, direction: str) -> int:
        """Count existing open positions for this symbol and direction."""
        try:
            # First check in-memory state
            if hasattr(BOT_STATE, 'get_positions_by_symbol'):
                mem_pos = BOT_STATE.get_positions_by_symbol(symbol)
                if mem_pos:
                    dir_lower = direction.lower()
                    side_aliases = ('long', 'buy') if dir_lower == 'long' else ('short', 'sell')
                    matching = [p for p in mem_pos if str(p.get('side', '')).lower() in side_aliases and str(p.get('status', 'open')).lower() in ('open', 'pending')]
                    return len(matching)

            table = 'forex_positions' if self.market_type == 'forex' else 'positions'
            side_val = 'buy' if direction.lower() == 'long' else ('sell' if direction.lower() == 'short' else direction.lower())
            response = self.sb.table(table).select('id').eq('symbol', symbol).in_('side', [direction.lower(), direction.upper(), side_val, side_val.upper()]).in_('status', ['OPEN', 'open']).execute()
            return len(response.data) if response and response.data else 0
        except Exception as e:
            log_error(MODULE, f"Error counting positions for {symbol} {direction}: {str(e)}")
            return 0

    def _execute_entry(self, symbol: str, direction: str, result: ReboteResult) -> bool:
        """Execute the entry via the execution service."""
        if not self.execution_service:
            log_warning(MODULE, "No execution service configured for ReboteMonitor")
            return False
            
        try:
            reason = f"REBOTE (Score: {result.score_final})"
            
            if self.market_type == 'forex':
                lots = result.detail.get('suggested_lots', 0.01)
                sl = result.detail.get('suggested_sl')
                tp = result.detail.get('suggested_tp')
                self.execution_service.open_forex_position(
                    symbol=symbol,
                    direction=direction,
                    lots=lots,
                    stop_loss=sl,
                    take_profit=tp,
                    reason=reason
                )
            else:
                self.execution_service.open_crypto_position(
                    symbol=symbol,
                    direction=direction,
                    reason=reason
                )
            log_info(MODULE, f"Entry executed for {symbol} {direction} via REBOTE")
            return True
        except Exception as e:
            log_error(MODULE, f"Error executing entry for {symbol} {direction}: {str(e)}")
            return False
