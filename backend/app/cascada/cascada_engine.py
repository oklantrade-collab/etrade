"""
CASCADA Pure Decision Engine.
eTrade v5.0 — Spec Section 3
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import pandas as pd

from app.cascada.config import CASCADA_PARAMS, LEVEL_DEFINITIONS
from app.cascada.giveback_monitor import evaluate_giveback, update_pnl_pico
from app.cascada.level_evaluator import check_rebote, check_continuacion


@dataclass
class CascadaResult:
    position_id: str
    symbol: str
    direction: str
    market_type: str = 'forex'
    current_level: int = 0
    previous_level: Optional[int] = None
    level_advanced: bool = False
    check_type: str = 'none'        # 'rebote' | 'continuacion' | 'giveback' | 'hold'
    decision: str = 'HOLD'          # 'CERRAR' | 'MANTENER' | 'GIVEBACK_CLOSE' | 'HOLD'
    cascade_hold: bool = False      # Whether to block external/discretionary closes
    pnl_current: float = 0.0
    pnl_pico: float = 0.0
    giveback_pct: float = 0.0
    signals: Dict[str, Any] = field(default_factory=dict)
    slope_table: Dict[str, Any] = field(default_factory=dict)
    detail: str = ''


class CascadaEngine:
    """
    Pure decision engine for extended trend positions originating from REBOTE.
    """
    def __init__(self, params: Dict[str, Any] = None):
        self.params = params or CASCADA_PARAMS

    def evaluate(
        self,
        position: Dict[str, Any],
        radar_snapshot: Dict[str, Any],
        radar_events: List[Dict[str, Any]],
        df_15m: Optional[pd.DataFrame] = None,
        df_higher_tf: Optional[pd.DataFrame] = None
    ) -> CascadaResult:
        """
        Evaluates a single position under CASCADA management.
        """
        pos_id = str(position.get('id', ''))
        symbol = str(position.get('symbol', '')).upper()
        direction = str(position.get('side', '')).lower()
        market_type = str(position.get('market_type', 'forex'))

        pnl_current = float(position.get('unrealized_pnl', 0.0) or position.get('unrealized_pnl_usd', 0.0) or 0.0)
        pnl_pico_stored = position.get('pnl_pico')
        pnl_pico = update_pnl_pico(pnl_current, float(pnl_pico_stored) if pnl_pico_stored is not None else None)

        prev_level = position.get('cascade_level')
        prev_level_int = int(prev_level) if prev_level is not None else 0

        # Section 2.4 Fail-safe: If RADAR published sin_datos, rely ONLY on giveback
        if radar_snapshot.get('status') == 'sin_datos':
            gb_res = evaluate_giveback(
                pnl_current, pnl_pico, 
                threshold_pct=self.params.get('giveback_threshold_pct', 0.50)
            )
            if gb_res['triggered']:
                return CascadaResult(
                    position_id=pos_id, symbol=symbol, direction=direction, market_type=market_type,
                    current_level=prev_level_int, previous_level=prev_level_int, level_advanced=False,
                    check_type='giveback', decision='GIVEBACK_CLOSE', cascade_hold=False,
                    pnl_current=pnl_current, pnl_pico=pnl_pico, giveback_pct=gb_res['giveback_pct'],
                    detail=f"SIN DATOS from RADAR: Forced close via giveback ({gb_res['detail']})"
                )
            return CascadaResult(
                position_id=pos_id, symbol=symbol, direction=direction, market_type=market_type,
                current_level=prev_level_int, previous_level=prev_level_int, level_advanced=False,
                check_type='hold', decision='HOLD', cascade_hold=False,
                pnl_current=pnl_current, pnl_pico=pnl_pico, giveback_pct=gb_res['giveback_pct'],
                detail="SIN DATOS from RADAR: Holding under giveback protection"
            )

        # 1. ALWAYS EVALUATE DYNAMIC GIVEBACK (Section 3.7)
        # Giveback bypasses cascade_hold and forces closure
        gb_res = evaluate_giveback(
            pnl_current, pnl_pico, 
            threshold_pct=self.params.get('giveback_threshold_pct', 0.50)
        )
        if gb_res['triggered']:
            return CascadaResult(
                position_id=pos_id,
                symbol=symbol,
                direction=direction,
                market_type=market_type,
                current_level=prev_level_int,
                previous_level=prev_level_int,
                level_advanced=False,
                check_type='giveback',
                decision='GIVEBACK_CLOSE',
                cascade_hold=False,
                pnl_current=pnl_current,
                pnl_pico=pnl_pico,
                giveback_pct=gb_res['giveback_pct'],
                detail=gb_res['detail']
            )

        # 2. Determine Current Level (N0 to N5) based on events
        current_level = self._detect_level(direction, radar_snapshot, radar_events, prev_level_int)
        level_advanced = current_level > prev_level_int

        # 3. If in N0 (Entry level), hold and wait for N1
        if current_level == 0:
            return CascadaResult(
                position_id=pos_id, symbol=symbol, direction=direction, market_type=market_type,
                current_level=0, previous_level=prev_level_int, level_advanced=False,
                check_type='hold', decision='HOLD', cascade_hold=False,
                pnl_current=pnl_current, pnl_pico=pnl_pico, giveback_pct=gb_res['giveback_pct'],
                detail="Position in N0 (Extreme entry, waiting for N1 EMA3/EMA9 cross)"
            )

        # 4. Check Rebote (Section 3.3a)
        rebote_eval = check_rebote(direction, radar_snapshot, pnl_current, current_level)
        if rebote_eval['is_rebote']:
            return CascadaResult(
                position_id=pos_id,
                symbol=symbol,
                direction=direction,
                market_type=market_type,
                current_level=current_level,
                previous_level=prev_level_int,
                level_advanced=level_advanced,
                check_type='rebote',
                decision='CERRAR',
                cascade_hold=False,
                pnl_current=pnl_current,
                pnl_pico=pnl_pico,
                giveback_pct=gb_res['giveback_pct'],
                signals={'rebote': rebote_eval},
                slope_table=radar_snapshot.get('slope_matrix', {}),
                detail=rebote_eval['detail']
            )

        # 5. Check Continuation Support Signals (Section 3.3b & 3.4)
        cont_eval = check_continuacion(
            direction, current_level, df_15m, df_higher_tf, self.params
        )

        if cont_eval['confirmed']:
            # Continuation confirmed -> Hold and activate cascade_hold=True
            return CascadaResult(
                position_id=pos_id,
                symbol=symbol,
                direction=direction,
                market_type=market_type,
                current_level=current_level,
                previous_level=prev_level_int,
                level_advanced=level_advanced,
                check_type='continuacion',
                decision='MANTENER',
                cascade_hold=True,
                pnl_current=pnl_current,
                pnl_pico=pnl_pico,
                giveback_pct=gb_res['giveback_pct'],
                signals={'continuation': cont_eval},
                slope_table=radar_snapshot.get('slope_matrix', {}),
                detail=f"N{current_level} continuation confirmed -> MANTENER (Hold locked)"
            )
        else:
            # Continuation weak or unconfirmed -> MANTENER without locking hold
            return CascadaResult(
                position_id=pos_id,
                symbol=symbol,
                direction=direction,
                market_type=market_type,
                current_level=current_level,
                previous_level=prev_level_int,
                level_advanced=level_advanced,
                check_type='hold',
                decision='HOLD',
                cascade_hold=False,
                pnl_current=pnl_current,
                pnl_pico=pnl_pico,
                giveback_pct=gb_res['giveback_pct'],
                signals={'continuation': cont_eval},
                slope_table=radar_snapshot.get('slope_matrix', {}),
                detail=f"N{current_level} holding without lock (Continuation support unconfirmed)"
            )

    def _detect_level(
        self, 
        direction: str, 
        radar_snapshot: Dict[str, Any], 
        events: List[Dict[str, Any]], 
        prev_level: int
    ) -> int:
        """
        Determines current cascade level based on discrete crossover events in position's direction.
        """
        is_short = direction.lower() in ('short', 'sell')
        expected_dir = 'bearish' if is_short else 'bullish'

        max_level = prev_level

        for ev in events:
            ev_type = ev.get('event_type', '')
            ev_dir = ev.get('direction', '')

            if ev_dir != expected_dir:
                continue

            if ev_type == 'cruce_EMA3_EMA9':
                max_level = max(max_level, 1)
            elif ev_type == 'cruce_EMA9_EMA20':
                max_level = max(max_level, 2)
            elif ev_type == 'cruce_EMA20_EMA50':
                max_level = max(max_level, 3)
            elif ev_type == 'cruce_EMA50_EMA200':
                max_level = max(max_level, 4)
            elif ev_type.startswith('cruce_fibonacci_'):
                max_level = max(max_level, 5)

        return min(max_level, self.params.get('max_cascade_level', 5))
