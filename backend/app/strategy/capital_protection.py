
"""
Sistema de Protección de Capital — 7 Reglas

Gestiona el ciclo de vida de una posición
para maximizar ganancias y minimizar pérdidas.

Compatible con:
  - Crypto: Binance Futures (BTC, ETH, SOL, ADA)
  - Forex:  IC Markets cTrader (EUR/USD, etc.)
  - Stocks: IB TWS (acciones US)
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict
from app.core.logger import log_info, log_error

# ── Configuración por mercado ─────────────────
PROTECTION_CONFIG = {
    'crypto_futures': {
        'be_trigger_pct':    0.003,  # +0.3%
        'be_buffer_pct':     0.0005, # +0.05%
        'trailing_levels': [
            # (trigger_pct, new_sl_pct)
            (0.003,  0.0005),  # +0.3% → SL a +0.05%
            (0.006,  0.002),   # +0.6% → SL a +0.2%
            (0.010,  0.005),   # +1.0% → SL a +0.5%
            (0.015,  0.008),   # +1.5% → SL a +0.8%
            (0.025,  0.015),   # +2.5% → SL a +1.5%
        ],
        'min_time_before_inverse_close': 2,
        # ciclos de 5m = 10 minutos
        'max_loss_before_inverse_close': 0.5,
        # cerrar por señal inversa solo si
        # pérdida < 50% del SL original
        'partial_close_tp1_pct':  0.008,  # +0.8%
        'partial_close_tp2_pct':  0.015,  # +1.5%
        'partial_close_ratio':    0.50,   # 50%
        'cooldown_cycles':        2,
        'counter_trend_size_pct': 0.50,
    },
    'forex_futures': {
        'be_trigger_pips':   8,
        'be_buffer_pips':    1,
        'trailing_levels_pips': [
            # (trigger_pips, new_sl_pips)
            (8,   1),    # +8 pips  → BE +1 pip
            (15,  5),    # +15 pips → SL a +5 pips
            (25,  12),   # +25 pips → SL a +12 pips
            (40,  25),   # +40 pips → SL a +25 pips
            (60,  40),   # +60 pips → SL a +40 pips
        ],
        'min_time_before_inverse_close': 3,
        # ciclos de 5m = 15 minutos
        'max_loss_before_inverse_close': 0.5,
        'partial_close_tp1_pips':  20,
        'partial_close_tp2_pips':  40,
        'partial_close_ratio':     0.50,
        'cooldown_cycles':         3,
        'counter_trend_size_pct':  0.50,
    },
    'stocks_spot': {
        'be_trigger_pct':    0.005,  # +0.5%
        'be_buffer_pct':     0.001,  # +0.1%
        'trailing_levels': [
            (0.005,  0.001),   # +0.5% → +0.1%
            (0.010,  0.004),   # +1.0% → +0.4%
            (0.020,  0.010),   # +2.0% → +1.0%
            (0.035,  0.020),   # +3.5% → +2.0%
            (0.050,  0.030),   # +5.0% → +3.0%
        ],
        'min_time_before_inverse_close': 4,
        'max_loss_before_inverse_close': 0.5,
        'partial_close_tp1_pct':  0.015,  # +1.5%
        'partial_close_tp2_pct':  0.030,  # +3.0%
        'partial_close_ratio':    0.50,
        'cooldown_cycles':        2,
        'counter_trend_size_pct': 0.50,
    },
}

# Pip sizes para Forex
PIP_SIZES = {
    'EURUSD': 0.0001, 'GBPUSD': 0.0001,
    'USDJPY': 0.01,   'USDCHF': 0.0001,
    'XAUUSD': 0.01,   'AUDUSD': 0.0001,
}

@dataclass
class ProtectionState:
    """
    Estado de protección de una posición.
    Se almacena en memory y opcionalmente se persiste.
    """
    position_id:       str
    symbol:            str
    side:              str
    entry_price:       float
    current_sl:        float
    original_sl:       float
    market_type:       str

    # Trailing
    trailing_level:    int   = 0
    highest_pnl_pct:   float = 0.0
    highest_price:     float = 0.0
    lowest_price:      float = 0.0

    # Break-Even
    be_activated:      bool  = False
    be_price:          float = 0.0

    # Partial Close
    partial_closed:    bool  = False
    partial_size:      float = 0.0
    remaining_size:    float = 0.0

    # Cooldown
    cycles_open:       int   = 0
    last_close_cycle:  int   = 0

    # Señal inversa
    inverse_signal_cycles: int = 0


def calculate_pnl(
    entry:   float,
    current: float,
    side:    str,
    symbol:  str = '',
    market_type: str = 'crypto_futures'
) -> dict:
    """Calcula el P&L en % y en pips."""
    if entry <= 0:
        return {'pct': 0.0, 'pips': 0.0, 'is_profit': False}

    is_long = side.lower() in ('long', 'buy')
    if is_long:
        pct  = (current - entry) / entry * 100
        diff = current - entry
    else:
        pct  = (entry - current) / entry * 100
        diff = entry - current

    pips = 0.0
    if market_type == 'forex_futures':
        pip = PIP_SIZES.get(symbol, 0.0001)
        pips = diff / pip

    return {
        'pct':       round(pct,  4),
        'pips':      round(pips, 1),
        'diff':      round(diff, 6),
        'is_profit': pct > 0,
    }


def evaluate_trailing_stop(
    state:         ProtectionState,
    current_price: float,
) -> dict:
    """
    REGLA 4: Trailing Stop Escalonado.
    Evalúa si el SL debe subir al siguiente nivel. El SL NUNCA retrocede.
    """
    cfg  = PROTECTION_CONFIG.get(state.market_type, {})
    side = state.side.lower()
    is_long = side in ('long', 'buy')
    entry = state.entry_price

    pnl = calculate_pnl(entry, current_price, side, state.symbol, state.market_type)

    if state.market_type == 'forex_futures':
        current_gain = pnl['pips']
        levels       = cfg.get('trailing_levels_pips', [])
        pip = PIP_SIZES.get(state.symbol, 0.0001)

        for i, (trigger, new_sl_pips) in enumerate(levels):
            level_idx = i + 1
            if current_gain >= trigger and state.trailing_level < level_idx:
                if is_long:
                    new_sl = entry + (new_sl_pips * pip)
                else:
                    new_sl = entry - (new_sl_pips * pip)

                # Verificar que el nuevo SL es mejor (nunca retrocede)
                if is_long:
                    if new_sl <= state.current_sl: continue
                else:
                    if new_sl >= state.current_sl: continue

                return {
                    'action':    'update_sl',
                    'new_sl':    round(new_sl, 6),
                    'new_level': level_idx,
                    'reason': (
                        f'Trailing nivel {level_idx}: '
                        f'+{trigger} pips alcanzados → SL a +{new_sl_pips} pips ({new_sl:.6f})'
                    ),
                }
    else:  # crypto / stocks
        current_gain = pnl['pct'] / 100
        levels       = cfg.get('trailing_levels', [])

        for i, (trigger, new_sl_pct) in enumerate(levels):
            level_idx = i + 1
            if current_gain >= trigger and state.trailing_level < level_idx:
                if is_long:
                    new_sl = entry * (1 + new_sl_pct)
                else:
                    new_sl = entry * (1 - new_sl_pct)

                if is_long:
                    if new_sl <= state.current_sl: continue
                else:
                    if new_sl >= state.current_sl: continue

                return {
                    'action':    'update_sl',
                    'new_sl':    round(new_sl, 8),
                    'new_level': level_idx,
                    'reason': (
                        f'Trailing nivel {level_idx}: '
                        f'+{trigger*100:.2f}% → SL a +{new_sl_pct*100:.2f}%'
                    ),
                }

    return {'action': 'none'}


def evaluate_break_even(
    state:         ProtectionState,
    current_price: float,
) -> dict:
    """
    REGLA 1: Break-Even Automático.
    Mueve el SL al precio de entrada + buffer al alcanzar el umbral.
    """
    if state.be_activated:
        return {'action': 'none'}

    cfg  = PROTECTION_CONFIG.get(state.market_type, {})
    entry = state.entry_price
    side  = state.side.lower()
    is_long = side in ('long', 'buy')

    pnl = calculate_pnl(entry, current_price, side, state.symbol, state.market_type)

    if state.market_type == 'forex_futures':
        trigger = cfg.get('be_trigger_pips', 8)
        buffer  = cfg.get('be_buffer_pips', 1)
        pip     = PIP_SIZES.get(state.symbol, 0.0001)

        if pnl['pips'] >= trigger:
            be_price = entry + (buffer * pip) if is_long else entry - (buffer * pip)
            return {
                'action':   'activate_be',
                'be_price': round(be_price, 6),
                'reason':   f'Break-Even: +{pnl["pips"]:.1f} pips ≥ {trigger} pips → SL a {be_price:.6f}'
            }
    else:  # crypto / stocks
        trigger = cfg.get('be_trigger_pct', 0.003)
        buffer  = cfg.get('be_buffer_pct', 0.0005)

        if pnl['pct'] / 100 >= trigger:
            be_price = entry * (1 + buffer) if is_long else entry * (1 - buffer)
            return {
                'action':   'activate_be',
                'be_price': round(be_price, 8),
                'reason':   f'Break-Even: +{pnl["pct"]:.3f}% ≥ {trigger*100:.2f}% → SL a {be_price:.8f}'
            }

    return {'action': 'none'}


def evaluate_inverse_signal(
    state:         ProtectionState,
    current_price: float,
    inverse_rule:  str,
) -> dict:
    """
    REGLA 2 + REGLA 5: Filtro inteligente para señales inversas.
    """
    cfg   = PROTECTION_CONFIG.get(state.market_type, {})
    pnl = calculate_pnl(state.entry_price, current_price, state.side, state.symbol, state.market_type)

    original_sl   = state.original_sl
    entry = state.entry_price
    original_risk = abs(entry - original_sl) / entry if entry > 0 else 0.01

    min_cycles    = cfg.get('min_time_before_inverse_close', 2)
    max_loss_ratio = cfg.get('max_loss_before_inverse_close', 0.5)

    if pnl['is_profit']:
        return {
            'action': 'close_market',
            'reason': f'Señal inversa {inverse_rule} con ganancia +{pnl["pct"]:.3f}% → Asegurar',
            'pnl': pnl, 'urgent': False,
        }

    loss_pct = abs(pnl['pct']) / 100
    loss_ratio = loss_pct / original_risk if original_risk > 0 else 1.0

    if state.cycles_open < min_cycles and loss_ratio < max_loss_ratio:
        state.inverse_signal_cycles += 1
        return {
            'action': 'wait_confirmation',
            'reason': f'Señal inversa {inverse_rule}: posición joven ({state.cycles_open} ciclos), esperando...',
            'pnl': pnl, 'cycles_waiting': state.inverse_signal_cycles,
        }

    if loss_ratio >= max_loss_ratio:
        return {
            'action': 'close_market',
            'reason': f'Señal inversa {inverse_rule}: pérdida alta {pnl["pct"]:.3f}% ({loss_ratio*100:.0f}% del SL) → Cerrar',
            'pnl': pnl, 'urgent': True,
        }

    if state.inverse_signal_cycles >= 2:
        return {
            'action': 'close_market',
            'reason': f'Señal inversa confirmada ({state.inverse_signal_cycles}x) → Cerrar pérdida controlada',
            'pnl': pnl, 'urgent': False,
        }

    return {'action': 'wait_confirmation', 'pnl': pnl}


def evaluate_partial_close(
    state:         ProtectionState,
    current_price: float,
) -> dict:
    """
    REGLA 6: Cierre Parcial en zonas de TP.
    """
    if state.partial_closed:
        return {'action': 'none'}

    cfg  = PROTECTION_CONFIG.get(state.market_type, {})
    pnl = calculate_pnl(state.entry_price, current_price, state.side, state.symbol, state.market_type)

    if state.market_type == 'forex_futures':
        tp1 = cfg.get('partial_close_tp1_pips', 20)
        ratio = cfg.get('partial_close_ratio', 0.50)
        if pnl['pips'] >= tp1:
            return {
                'action':    'partial_close',
                'close_pct': ratio, 'tp_level': 1, 'move_sl_to_be': True,
                'reason':    f'TP1 alcanzado: +{pnl["pips"]:.1f} pips ≥ {tp1} pips → Cerrar {ratio*100:.0f}% + SL a BE'
            }
    else:
        tp1_pct = cfg.get('partial_close_tp1_pct', 0.008)
        ratio   = cfg.get('partial_close_ratio', 0.50)
        if pnl['pct'] / 100 >= tp1_pct:
            return {
                'action':    'partial_close',
                'close_pct': ratio, 'tp_level': 1, 'move_sl_to_be': True,
                'reason':    f'TP1 alcanzado: +{pnl["pct"]:.3f}% ≥ {tp1_pct*100:.2f}% → Cerrar {ratio*100:.0f}% + SL a BE'
            }

    return {'action': 'none'}


def evaluate_counter_trend_sizing(
    signal_direction: str,
    snap:             dict,
    market_type:      str = 'crypto_futures'
) -> dict:
    """
    REGLA 3: Reducción de tamaño en señales contra-tendencia.
    """
    cfg = PROTECTION_CONFIG.get(market_type, {})
    size_reduction = cfg.get('counter_trend_size_pct', 0.50)
    flags = []

    sar_4h = int(snap.get('sar_trend_4h', 0))
    if signal_direction.lower() in ('long', 'buy') and sar_4h < 0:
        flags.append('SAR 4H bajista vs LONG')
    elif signal_direction.lower() in ('short', 'sell') and sar_4h > 0:
        flags.append('SAR 4H alcista vs SHORT')

    mtf = float(snap.get('mtf_score', 0))
    if signal_direction.lower() in ('long', 'buy') and mtf < 0.20:
        flags.append(f'MTF débil para LONG ({mtf:.2f})')
    elif signal_direction.lower() in ('short', 'sell') and mtf > -0.20:
        flags.append(f'MTF débil para SHORT ({mtf:.2f})')

    adx = float(snap.get('adx', 0))
    if adx > 35:
        plus_di  = float(snap.get('plus_di', 0))
        minus_di = float(snap.get('minus_di', 0))
        if signal_direction.lower() in ('long','buy') and minus_di > plus_di:
            flags.append(f'ADX fuerte bajista ({adx:.1f})')
        elif signal_direction.lower() not in ('long','buy') and plus_di > minus_di:
            flags.append(f'ADX fuerte alcista ({adx:.1f})')

    is_counter = len(flags) >= 2
    return {
        'is_counter_trend': is_counter,
        'flags': flags,
        'sizing_factor': size_reduction if is_counter else 1.0,
        'reason': f'Counter-trend: {len(flags)} flags → sizing {"50%" if is_counter else "100%"}'
    }


def check_cooldown(
    symbol:           str,
    last_close_cycle: int,
    current_cycle:    int,
    market_type:      str = 'crypto_futures'
) -> dict:
    """
    REGLA 7: Cooldown entre operaciones.
    """
    cfg      = PROTECTION_CONFIG.get(market_type, {})
    cooldown = cfg.get('cooldown_cycles', 2)
    cycles   = current_cycle - last_close_cycle
    in_cooldown = cycles < cooldown

    return {
        'in_cooldown': in_cooldown,
        'cycles_waited': cycles, 'cycles_needed': cooldown,
        'reason': f'{"⏳ Cooldown activo" if in_cooldown else "✅ Cooldown OK"}: {cycles}/{cooldown} ciclos'
    }


def evaluate_all_protections(
    state:         ProtectionState,
    current_price: float,
    snap:          dict,
    inverse_rule:  Optional[str] = None,
) -> dict:
    """
    Función principal de evaluación por prioridades.
    """
    actions = []

    # 1. Break-Even
    be = evaluate_break_even(state, current_price)
    if be['action'] == 'activate_be':
        actions.append({'priority': 1, 'type': 'break_even', **be})

    # 2. Trailing Stop
    trail = evaluate_trailing_stop(state, current_price)
    if trail['action'] == 'update_sl':
        actions.append({'priority': 2, 'type': 'trailing', **trail})

    # 3. Partial Close
    partial = evaluate_partial_close(state, current_price)
    if partial['action'] == 'partial_close':
        actions.append({'priority': 3, 'type': 'partial_close', **partial})

    # 4. Señal Inversa
    if inverse_rule:
        inv = evaluate_inverse_signal(state, current_price, inverse_rule)
        if inv['action'] in ('close_market', 'wait_confirmation'):
            actions.append({'priority': 4, 'type': 'inverse_signal', **inv})

    if actions:
        primary = min(actions, key=lambda x: x['priority'])
        return {
            'has_action': True, 'primary': primary, 'all_actions': actions,
            'pnl': calculate_pnl(state.entry_price, current_price, state.side, state.symbol, state.market_type),
        }

    return {
        'has_action': False, 'primary': None, 'all_actions': [],
        'pnl': calculate_pnl(state.entry_price, current_price, state.side, state.symbol, state.market_type),
    }
