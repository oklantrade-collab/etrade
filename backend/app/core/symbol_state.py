"""
State Machine para control de posiciones por símbolo.
Previene entradas duplicadas y gestiona transiciones de dirección.
Soporta DCA (Múltiples posiciones) y unifica LONG/SHORT.
"""

from enum import Enum
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd
from app.core.logger import log_info, log_error
from app.core.supabase_client import get_supabase

class SymbolState(Enum):
    NEUTRAL  = 'neutral'
    LONG     = 'long'
    SHORT    = 'short'
    CLOSING  = 'closing'
    WAITING  = 'waiting'
    AMBIGUOUS = 'ambiguous'

@dataclass
class SymbolContext:
    symbol: str
    state: SymbolState = SymbolState.NEUTRAL
    open_positions: list = field(default_factory=list)
    last_signal: Optional[str] = None
    last_state_change: Optional[datetime] = None
    waiting_cycles: int = 0
    flip_pending: bool = False
    flip_direction: Optional[str] = None
    flip_score: float = 0.0
    ambiguous_cycles: int = 0

    def transition_to(self, new_state: SymbolState, reason: str = ''):
        old = self.state.value
        if old != new_state.value:
            self.state = new_state
            self.last_state_change = datetime.now(timezone.utc)
            log_info('STATE_MACHINE', f'{self.symbol}: {old} → {new_state.value} ({reason})')
            # Trigger DB sync
            return True
        return False

class SymbolStateMachine:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._contexts: dict[str, SymbolContext] = {}

    def get(self, symbol: str) -> SymbolContext:
        if symbol not in self._contexts:
            self._contexts[symbol] = SymbolContext(symbol=symbol)
            self.load_from_db(symbol)
        return self._contexts[symbol]

    def sync_from_positions(self, symbol: str, positions: list):
        ctx = self.get(symbol)
        open_pos = [p for p in positions if p.get('status') == 'open']
        ctx.open_positions = open_pos

        if not open_pos:
            if ctx.state not in (SymbolState.WAITING, SymbolState.CLOSING, SymbolState.AMBIGUOUS):
                ctx.state = SymbolState.NEUTRAL
        else:
            sides = set(p.get('side', 'long').lower() for p in open_pos)
            # Normalize buy->long, sell->short
            if 'long' in sides or 'buy' in sides:
                ctx.state = SymbolState.LONG
            elif 'short' in sides or 'sell' in sides:
                ctx.state = SymbolState.SHORT

    def can_open(self, symbol: str, direction: str, current_price: float, max_positions: int = 4) -> dict:
        ctx = self.get(symbol)
        state = ctx.state
        direction = 'long' if direction.lower() == 'buy' else ('short' if direction.lower() == 'sell' else direction.lower())

        if state == SymbolState.NEUTRAL:
            return {'allowed': True, 'reason': 'Estado NEUTRAL'}

        if state == SymbolState.LONG:
            if direction == 'short':
                return {'allowed': True, 'is_flip': True, 'close_first': True, 'reason': 'Flip LONG→SHORT: cerrar primero'}
            else:
                # DCA / Accumulation allowed if < max_positions and price is better
                if len(ctx.open_positions) < max_positions:
                    last_pos = sorted(ctx.open_positions, key=lambda x: x.get('opened_at', ''), reverse=True)[0]
                    last_entry = float(last_pos.get('entry_price') or last_pos.get('avg_entry_price') or 0)
                    if current_price < last_entry:
                        return {'allowed': True, 'is_flip': False, 'close_first': False, 'reason': f'DCA LONG: {current_price} < {last_entry}'}
                    else:
                        return {'allowed': False, 'reason': f'Precio no mejora costo LONG ({current_price} >= {last_entry})'}
                return {'allowed': False, 'reason': f'Límite de {max_positions} posiciones LONG alcanzado'}

        if state == SymbolState.SHORT:
            if direction == 'long':
                return {'allowed': True, 'is_flip': True, 'close_first': True, 'reason': 'Flip SHORT→LONG: cerrar primero'}
            else:
                # DCA / Accumulation
                if len(ctx.open_positions) < max_positions:
                    last_pos = sorted(ctx.open_positions, key=lambda x: x.get('opened_at', ''), reverse=True)[0]
                    last_entry = float(last_pos.get('entry_price') or last_pos.get('avg_entry_price') or 0)
                    if current_price > last_entry:
                        return {'allowed': True, 'is_flip': False, 'close_first': False, 'reason': f'DCA SHORT: {current_price} > {last_entry}'}
                    else:
                        return {'allowed': False, 'reason': f'Precio no mejora costo SHORT ({current_price} <= {last_entry})'}
                return {'allowed': False, 'reason': f'Límite de {max_positions} posiciones SHORT alcanzado'}

        if state in (SymbolState.CLOSING, SymbolState.WAITING, SymbolState.AMBIGUOUS):
            return {'allowed': False, 'reason': f'Estado {state.value} (Waiting: {ctx.waiting_cycles}, Ambiguous: {ctx.ambiguous_cycles})'}

        return {'allowed': False, 'reason': f'Estado desconocido: {state}'}

    def can_close(self, symbol: str) -> dict:
        ctx = self.get(symbol)
        if ctx.state == SymbolState.NEUTRAL:
            return {'allowed': False, 'reason': 'Sin posición abierta'}
        return {'allowed': True, 'reason': 'Cierre permitido'}

    def on_position_opened(self, symbol: str, direction: str, position: dict):
        ctx = self.get(symbol)
        ctx.open_positions.append(position)
        direction = 'long' if direction.lower() == 'buy' else ('short' if direction.lower() == 'sell' else direction.lower())
        new_state = SymbolState.LONG if direction == 'long' else SymbolState.SHORT
        ctx.transition_to(new_state, f'Posición abierta {direction.upper()}')
        ctx.flip_pending = False
        ctx.flip_direction = None
        self.save_to_db(symbol)

    def on_position_closed(self, symbol: str, close_reason: str, all_closed: bool = True):
        ctx = self.get(symbol)
        if all_closed:
            ctx.open_positions = []
            reason_lower = close_reason.lower()
            if 'sl' in reason_lower or 'time_sl' in reason_lower:
                ctx.transition_to(SymbolState.WAITING, f'SL activado: {close_reason}')
                ctx.waiting_cycles = 3
            elif ctx.flip_pending:
                ctx.transition_to(SymbolState.CLOSING, 'Flip pendiente')
            else:
                ctx.transition_to(SymbolState.NEUTRAL, f'Cerrado: {close_reason}')
            self.save_to_db(symbol)

    def tick_waiting(self, symbol: str):
        ctx = self.get(symbol)
        if ctx.state == SymbolState.WAITING:
            ctx.waiting_cycles -= 1
            if ctx.waiting_cycles <= 0:
                ctx.transition_to(SymbolState.NEUTRAL, 'Cooldown completado')
            self.save_to_db(symbol)

    def set_ambiguous(self, symbol: str, reason: str = ''):
        ctx = self.get(symbol)
        ctx.transition_to(SymbolState.AMBIGUOUS, reason)
        ctx.ambiguous_cycles = 2
        self.save_to_db(symbol)

    def tick_ambiguous(self, symbol: str):
        ctx = self.get(symbol)
        if ctx.state == SymbolState.AMBIGUOUS:
            ctx.ambiguous_cycles -= 1
            if ctx.ambiguous_cycles <= 0:
                ctx.transition_to(SymbolState.NEUTRAL, 'Ambigüedad resuelta')
            self.save_to_db(symbol)

    def save_to_db(self, symbol: str):
        """Persiste el estado actual en market_snapshot."""
        ctx = self.get(symbol)
        try:
            sb = get_supabase()
            sb.table('market_snapshot').update({
                'symbol_state': ctx.state.value,
                'waiting_cycles': ctx.waiting_cycles,
                'flip_pending': ctx.flip_pending,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }).eq('symbol', symbol).execute()
        except Exception as e:
            log_error('STATE_MACHINE', f'Error guardando estado para {symbol}: {e}')

    def load_from_db(self, symbol: str):
        """Carga el estado desde market_snapshot."""
        try:
            sb = get_supabase()
            res = sb.table('market_snapshot').select('symbol_state, waiting_cycles, flip_pending').eq('symbol', symbol).maybe_single().execute()
            if res and res.data:
                ctx = self.get(symbol)
                state_str = res.data.get('symbol_state', 'neutral')
                try:
                    ctx.state = SymbolState(state_str)
                except:
                    ctx.state = SymbolState.NEUTRAL
                ctx.waiting_cycles = res.data.get('waiting_cycles', 0)
                ctx.flip_pending = res.data.get('flip_pending', False)
        except Exception as e:
            log_error('STATE_MACHINE', f'Error cargando estado para {symbol}: {e}')


def detect_market_ambiguity(snap: dict) -> dict:
    flags = []
    mtf = float(snap.get('mtf_score', 0))
    if -0.20 < mtf < 0.20:
        flags.append(f'MTF neutro ({mtf:.2f})')

    sar_4h  = int(snap.get('sar_trend_4h',  0))
    sar_15m = int(snap.get('sar_trend_15m', 0))
    if sar_4h != 0 and sar_15m != 0 and sar_4h != sar_15m:
        flags.append(f'SAR divergente: 4h={sar_4h} 15m={sar_15m}')

    adx = float(snap.get('adx', 25))
    if adx < 15:
        flags.append(f'ADX muy débil ({adx:.1f})')

    fib = int(snap.get('fibonacci_zone', 0))
    if fib == 0:
        flags.append('Precio en BASIS (zona 0)')

    is_ambiguous = len(flags) >= 2
    return {
        'is_ambiguous': is_ambiguous,
        'flags': flags,
        'flag_count': len(flags),
        'reason': 'Ambiguo: ' + ', '.join(flags) if is_ambiguous else 'Mercado con dirección',
    }
