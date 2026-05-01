"""
Stop Loss Virtual con Modo Recuperación (SLVM)

Arquitectura:
  NIVEL 1 — Stop Loss Virtual (SLV):
    Precio calculado internamente.
    NO se envía al exchange.
    Se monitorea en cada ciclo de 5m.
    
  NIVEL 2 — Modo Recuperación (MR):
    Se activa cuando precio toca el SLV.
    Objetivo único: cerrar en 0 o < 3 pips.
    El trailing stop sigue activo durante MR.
    Máximo N ciclos de 5m (evitar espera infinita).
    
  NIVEL 3 — SL Backstop (siempre activo):
    Si el precio sigue cayendo más allá del
    SLV sin recuperarse en tiempo máximo
    → cerrar al mejor precio disponible.

Compatible con: Crypto, Forex, Stocks
"""

from datetime import datetime, timezone
from app.core.logger import log_info, log_warning, log_error

MODULE = 'SLVM'

# ── Configuración por mercado ─────────────────
SLVM_CONFIG = {
    'crypto_futures': {
        'slv_method':           'fibonacci',
        'slv_fallback_pct':     0.02,       # 2% si no hay Fib
        'slv_fibonacci_band':   'lower_1',  # banda preferida

        'recovery_max_cycles':  12,         # 12 × 5m = 60 min
        'recovery_target_pips': 0,          # objetivo: 0 pips
        'recovery_max_loss_pips': 3,
        'recovery_buffer_pct':  0.0002,     # 0.02% = "en cero"
    },
    'forex_futures': {
        'slv_method':           'fibonacci',
        'slv_fallback_pips':    15,
        'slv_fibonacci_band':   'lower_1',

        'recovery_max_cycles':  8,          # 8 × 5m = 40 min
        'recovery_target_pips': 0,
        'recovery_max_loss_pips': 3,
        'recovery_buffer_pips': 1,          # ± 1 pip = "en cero"
    },
    'stocks_spot': {
        'slv_method':           'pct',
        'slv_fallback_pct':     0.015,      # 1.5%
        'slv_fibonacci_band':   'lower_1',

        'recovery_max_cycles':  24,         # 24 × 5m = 120 min
        'recovery_target_pips': 0,
        'recovery_max_loss_pips': 3,
        'recovery_buffer_pct':  0.001,      # 0.1%
    },
}

PIP_SIZES = {
    'EURUSD': 0.0001, 'GBPUSD': 0.0001,
    'USDJPY': 0.01,   'XAUUSD': 0.01,
    'BTCUSDT': 1.0,   'ETHUSDT': 0.1,
    'SOLUSDT': 0.01,  'ADAUSDT': 0.0001,
    # Stocks use percentage-based, but default to 0.01
}


def _get_pip_size(symbol: str, market_type: str) -> float:
    """Get pip size for a symbol. For stocks, use $0.01."""
    if market_type == 'stocks_spot':
        return 0.01
    return PIP_SIZES.get(symbol, 0.0001)


# ════════════════════════════════════════════
# CÁLCULO DEL SLV AL ABRIR POSICIÓN
# ════════════════════════════════════════════

def calculate_slv(
    entry_price:  float,
    side:         str,
    symbol:       str,
    snap:         dict,
    market_type:  str = 'crypto_futures',
) -> dict:
    """
    Calcula el precio del Stop Loss Virtual.

    Para BUY (LONG):
      SLV = banda Fibonacci lower_1 actual
      Si no hay banda: entry × (1 - slv_pct) o entry - fallback_pips

    Para SELL (SHORT):
      SLV = banda Fibonacci upper_1 actual
      Si no hay banda: entry × (1 + slv_pct) o entry + fallback_pips

    El SLV NO genera orden en el exchange.
    """
    cfg  = SLVM_CONFIG.get(market_type, SLVM_CONFIG['crypto_futures'])
    band = cfg.get('slv_fibonacci_band', 'lower_1')
    pip_size = _get_pip_size(symbol, market_type)

    if side.lower() in ('long', 'buy'):
        fib_val = float(snap.get(band, 0) or 0)

        if fib_val > 0 and fib_val < entry_price:
            slv_price = fib_val
            source    = f'fibonacci_{band}'
        else:
            if market_type == 'forex_futures':
                fallback_pips = cfg.get('slv_fallback_pips', 15)
                slv_price = entry_price - (fallback_pips * pip_size)
                source    = f'fallback_{fallback_pips}pips'
            else:
                pct       = cfg.get('slv_fallback_pct', 0.02)
                slv_price = entry_price * (1 - pct)
                source    = f'fallback_{pct*100:.1f}pct'

    else:  # short, sell
        upper_band = band.replace('lower', 'upper')
        fib_val    = float(snap.get(upper_band, 0) or 0)

        if fib_val > 0 and fib_val > entry_price:
            slv_price = fib_val
            source    = f'fibonacci_{upper_band}'
        else:
            if market_type == 'forex_futures':
                fallback_pips = cfg.get('slv_fallback_pips', 15)
                slv_price = entry_price + (fallback_pips * pip_size)
                source    = f'fallback_{fallback_pips}pips'
            else:
                pct       = cfg.get('slv_fallback_pct', 0.02)
                slv_price = entry_price * (1 + pct)
                source    = f'fallback_{pct*100:.1f}pct'

    distance_pips = abs(entry_price - slv_price) / pip_size
    distance_pct  = abs(entry_price - slv_price) / entry_price * 100 if entry_price > 0 else 0

    return {
        'slv_price':     round(slv_price, 8),
        'source':        source,
        'distance_pips': round(distance_pips, 1),
        'distance_pct':  round(distance_pct, 4),
    }


# ════════════════════════════════════════════
# VERIFICACIÓN: ¿EL PRECIO TOCÓ EL SLV?
# ════════════════════════════════════════════

def check_slv_trigger(
    position:      dict,
    current_price: float,
) -> bool:
    """
    Verifica si el precio alcanzó el SLV.
    Si ya está en modo recuperación → False.
    """
    if position.get('recovery_mode'):
        return False

    slv_price = float(position.get('slv_price', 0) or 0)
    if slv_price <= 0:
        return False

    side = str(position.get('side', 'long')).lower()

    if side in ('long', 'buy'):
        return current_price <= slv_price
    else:
        return current_price >= slv_price


# ════════════════════════════════════════════
# MODO RECUPERACIÓN: LÓGICA PRINCIPAL
# ════════════════════════════════════════════

def evaluate_recovery_mode(
    position:      dict,
    current_price: float,
    snap:          dict,
    symbol:        str,
    market_type:   str = 'crypto_futures',
) -> dict:
    """
    Función principal del Modo Recuperación.
    Se llama en cada ciclo de 5m cuando recovery_mode = True.

    Evalúa 4 condiciones de salida en orden:

    SALIDA 1 — TRAILING GAIN:
      Si trailing subió y ahora hay ganancia → cerrar con ganancia

    SALIDA 2 — ZERO LOSS (óptima):
      Si precio regresó al entry ± buffer → cerrar en 0 pips

    SALIDA 3 — MIN LOSS (aceptable):
      Si pérdida ≤ max_loss_pips Y señal de giro → cerrar con ≤ 3 pips

    SALIDA 4 — TIMEOUT (último recurso):
      Si se agotaron los ciclos máximos → cerrar al precio actual
    """
    cfg = SLVM_CONFIG.get(market_type, SLVM_CONFIG['crypto_futures'])
    pip_size = _get_pip_size(symbol, market_type)

    # Extract position data with fallbacks
    entry_price = float(
        position.get('avg_entry_price') or
        position.get('entry_price') or
        position.get('avg_price') or 0
    )
    side = str(position.get('side', 'long')).lower()
    recovery_cycles = int(position.get('recovery_cycles', 0) or 0)
    max_cycles = int(
        position.get('recovery_max_cycles') or
        cfg.get('recovery_max_cycles', 12)
    )
    trailing_sl = float(position.get('trailing_sl_price', 0) or 0)

    buffer_pct  = cfg.get('recovery_buffer_pct', 0.0002)
    buffer_pips = cfg.get('recovery_buffer_pips', 1)
    max_loss_pips = cfg.get('recovery_max_loss_pips', 3)

    # P&L in pips
    if side in ('long', 'buy'):
        pnl_pips = (current_price - entry_price) / pip_size
        zero_zone_low  = entry_price - (buffer_pips * pip_size if market_type == 'forex_futures' else entry_price * buffer_pct)
        zero_zone_high = entry_price + (buffer_pips * pip_size if market_type == 'forex_futures' else entry_price * buffer_pct)
    else:
        pnl_pips = (entry_price - current_price) / pip_size
        zero_zone_low  = entry_price - (buffer_pips * pip_size if market_type == 'forex_futures' else entry_price * buffer_pct)
        zero_zone_high = entry_price + (buffer_pips * pip_size if market_type == 'forex_futures' else entry_price * buffer_pct)

    # Track lowest/highest price in recovery
    lowest_in_recovery = float(position.get('lowest_price_in_recovery') or current_price)
    if side in ('long', 'buy'):
        new_lowest = min(lowest_in_recovery, current_price)
    else:
        new_lowest = max(lowest_in_recovery, current_price)

    new_cycle = recovery_cycles + 1

    # ── SALIDA 1: Trailing con ganancia ───────
    if pnl_pips > 0:
        return {
            'should_close':     True,
            'action':           'close_gain',
            'exit_type':        'trailing_gain',
            'pnl_pips':         round(pnl_pips, 1),
            'new_lowest':       new_lowest,
            'recovery_cycles':  new_cycle,
            'reason': (
                f'MR: Precio recuperó a ganancia '
                f'+{pnl_pips:.1f} pips → cerrar con ganancia'
            ),
        }

    # ── SALIDA 2: Zero Loss ───────────────────
    in_zero_zone = zero_zone_low <= current_price <= zero_zone_high
    if in_zero_zone:
        return {
            'should_close':     True,
            'action':           'close_zero',
            'exit_type':        'zero_loss',
            'pnl_pips':         round(pnl_pips, 1),
            'new_lowest':       new_lowest,
            'recovery_cycles':  new_cycle,
            'reason': (
                f'MR: Precio regresó a zona cero '
                f'({current_price:.6f} ≈ {entry_price:.6f}) → cerrar en 0 pips'
            ),
        }

    # ── SALIDA 3: Pérdida mínima ≤ 3 pips ────
    near_entry = abs(pnl_pips) <= max_loss_pips
    market_turning = _detect_micro_reversal(snap, side, market_type)

    if near_entry and market_turning['detected']:
        return {
            'should_close':     True,
            'action':           'close_min_loss',
            'exit_type':        'min_loss',
            'pnl_pips':         round(pnl_pips, 1),
            'new_lowest':       new_lowest,
            'recovery_cycles':  new_cycle,
            'reversal_signal':  market_turning,
            'reason': (
                f'MR: Pérdida mínima {pnl_pips:.1f} pips '
                f'(≤ {max_loss_pips}) + giro detectado '
                f'({market_turning["signal"]}) → cerrar controlado'
            ),
        }

    # ── SALIDA 3.5: Cierre por Pánico / Aceleración Bajista ──
    # Si la pérdida supera el SL Virtual (ej. -2%) y vemos fuerte presión en contra
    current_loss_pct = abs(pnl_pips * pip_size / entry_price * 100) if entry_price > 0 else 0
    
    # Tolerancia mínima antes de evaluar pánico (ej. 1.5% o la mitad del Hard Stop)
    max_loss_hard = float(position.get('sl_max_loss_hard') or cfg.get('sl_max_loss_hard', 10.0))
    panic_threshold = min(max_loss_hard * 0.4, 2.0) # Evaluamos pánico si cae > 2% o 40% del Hard Stop
    
    if current_loss_pct >= panic_threshold:
        panic_signal = _detect_panic_acceleration(snap, side)
        if panic_signal['detected']:
            return {
                'should_close':     True,
                'action':           'close_panic',
                'exit_type':        'momentum_panic',
                'pnl_pips':         round(pnl_pips, 1),
                'new_lowest':       new_lowest,
                'recovery_cycles':  new_cycle,
                'reason': (
                    f'MR: Aceleración en contra detectada ({panic_signal["reason"]}). '
                    f'Cierre predictivo al {pnl_pips:.1f} pips para evitar Hard Stop.'
                ),
            }

    # ── SALIDA 4: Hard Stop (Seguridad Máxima) ──
    if current_loss_pct >= max_loss_hard:
        return {
            'should_close':     True,
            'action':           'close_hard_stop',
            'exit_type':        'hard_stop',
            'pnl_pips':         round(pnl_pips, 1),
            'new_lowest':       new_lowest,
            'recovery_cycles':  new_cycle,
            'reason': (
                f'MR: Hard Stop alcanzado ({current_loss_pct:.1f}% >= {max_loss_hard}%). '
                f'Cerrando inmediatamente para proteger capital.'
            ),
        }

    # ── SALIDA 5: Timeout ─────────────────────
    if recovery_cycles >= max_cycles:
        return {
            'should_close':     True,
            'action':           'close_timeout',
            'exit_type':        'timeout',
            'pnl_pips':         round(pnl_pips, 1),
            'new_lowest':       new_lowest,
            'recovery_cycles':  new_cycle,
            'reason': (
                f'MR: Timeout ({recovery_cycles}/{max_cycles} ciclos) → '
                f'cerrar al mejor precio. P&L: {pnl_pips:.1f} pips'
            ),
        }

    # ── HOLD: Seguir esperando ────────────────
    return {
        'should_close':     False,
        'action':           'hold',
        'exit_type':        None,
        'pnl_pips':         round(pnl_pips, 1),
        'new_lowest':       new_lowest,
        'recovery_cycles':  new_cycle,
        'reason': (
            f'MR: Ciclo {new_cycle}/{max_cycles}. '
            f'PnL: {pnl_pips:.1f} pips. Esperando recuperación...'
        ),
    }


def _detect_panic_acceleration(
    snap: dict,
    side: str
) -> dict:
    """
    Evalúa si hay una aceleración fuerte en contra del trade.
    Combina Momentum (MTF), Fuerza de tendencia (ADX) y Acción de precio (PineScript).
    """
    pine = str(snap.get('pinescript_signal', '') or '')
    mtf = float(snap.get('mtf_score', 0) or 0)
    adx = float(snap.get('adx', 0) or 0)
    macd_h = float(snap.get('macd_histogram', 0) or snap.get('macd_hist', 0) or 0)

    detected = False
    reason = ""

    if side in ('long', 'buy'):
        # Para LONG, pánico es caída fuerte
        if mtf < -0.4 and adx > 25 and pine in ('Sell', 'S', 'Strong Sell'):
            detected = True
            reason = f"Fuerte presión bajista (MTF: {mtf:.2f}, ADX: {adx:.1f})"
        elif mtf < -0.6:
            detected = True
            reason = f"Colapso de Momentum (MTF: {mtf:.2f})"
    else:
        # Para SHORT, pánico es subida fuerte
        if mtf > 0.4 and adx > 25 and pine in ('Buy', 'B', 'Strong Buy'):
            detected = True
            reason = f"Fuerte presión alcista (MTF: {mtf:.2f}, ADX: {adx:.1f})"
        elif mtf > 0.6:
            detected = True
            reason = f"Explosión de Momentum (MTF: {mtf:.2f})"

    return {
        'detected': detected,
        'reason': reason
    }

def _detect_micro_reversal(
    snap:        dict,
    side:        str,
    market_type: str
) -> dict:
    """
    Detecta señales de micro-reversión en 5m.
    Necesita >= 2 señales confirmando giro favorable.
    """
    signals_found = []

    pine = str(snap.get('pinescript_signal', '') or '')
    # Support multiple SAR field names across markets
    sar_15m = int(snap.get('sar_trend_15m', 0) or snap.get('sar_trend', 0) or 0)
    sar_dir = str(snap.get('psar_direction', '') or '')
    mtf     = float(snap.get('mtf_score', 0) or 0)
    macd_h  = float(snap.get('macd_histogram', 0) or snap.get('macd_hist', 0) or 0)

    if side in ('long', 'buy'):
        if pine in ('Buy', 'B'):
            signals_found.append('Pine=Buy')
        if sar_15m > 0 or sar_dir == 'bullish':
            signals_found.append('SAR+')
        if mtf > 0.20:
            signals_found.append(f'MTF={mtf:.2f}')
        if macd_h > 0:
            signals_found.append('MACD+')
    else:
        if pine in ('Sell', 'S'):
            signals_found.append('Pine=Sell')
        if sar_15m < 0 or sar_dir == 'bearish':
            signals_found.append('SAR-')
        if mtf < -0.20:
            signals_found.append(f'MTF={mtf:.2f}')
        if macd_h < 0:
            signals_found.append('MACD-')

    detected = len(signals_found) >= 2

    return {
        'detected':  detected,
        'signals':   signals_found,
        'signal':    '+'.join(signals_found) if signals_found else 'ninguna',
        'strength':  len(signals_found),
    }


# ════════════════════════════════════════════
# ACTIVACIÓN DEL MODO RECUPERACIÓN
# ════════════════════════════════════════════

def activate_recovery_mode_sync(
    position:      dict,
    current_price: float,
    symbol:        str,
    market_type:   str,
    supabase,
    table_name:    str = 'positions',
):
    """
    Activa el Modo Recuperación cuando el precio toca el SLV.
    Versión sincrónica compatible con todos los mercados.
    """
    pos_id    = position.get('id')
    entry     = float(
        position.get('avg_entry_price') or
        position.get('entry_price') or
        position.get('avg_price') or 0
    )
    slv_price = float(position.get('slv_price', 0) or 0)
    pip_size  = _get_pip_size(symbol, market_type)
    pip_loss  = abs(current_price - entry) / pip_size
    cfg       = SLVM_CONFIG.get(market_type, SLVM_CONFIG['crypto_futures'])
    max_cycles = cfg.get('recovery_max_cycles', 12)

    log_info(MODULE,
        f'🟡 SLV ACTIVADO [{symbol}]: '
        f'precio={current_price:.6f} tocó SLV={slv_price:.6f} '
        f'({pip_loss:.1f} pips). Iniciando Modo Recuperación...'
    )

    try:
        supabase.table(table_name).update({
            'slv_triggered':            True,
            'slv_triggered_at':         datetime.now(timezone.utc).isoformat(),
            'slv_triggered_price':      current_price,
            'recovery_mode':            True,
            'recovery_cycles':          0,
            'recovery_max_cycles':      max_cycles,
            'recovery_target_price':    entry,
            'lowest_price_in_recovery': current_price,
        }).eq('id', pos_id).execute()
    except Exception as e:
        log_error(MODULE, f'Error activando MR en DB: {e}')

    # Update local dict
    position['recovery_mode']            = True
    position['recovery_cycles']          = 0
    position['recovery_max_cycles']      = max_cycles
    position['recovery_target_price']    = entry
    position['lowest_price_in_recovery'] = current_price
    position['slv_triggered']            = True

    _send_telegram_alert(
        f'🟡 MODO RECUPERACIÓN [{symbol}]\n'
        f'SLV tocado: {slv_price:.6f}\n'
        f'Precio actual: {current_price:.6f}\n'
        f'Pérdida actual: {pip_loss:.1f} pips\n'
        f'Target: {entry:.6f} (0 pips)\n'
        f'Tiempo máx: {max_cycles * 5} min\n'
        f'⚡ Buscando recuperación...'
    )


def update_recovery_cycle_sync(
    position:      dict,
    result:        dict,
    supabase,
    table_name:    str = 'positions',
):
    """
    Actualiza ciclos y tracking de recovery en DB.
    Llamado en cada ciclo de 5m mientras recovery_mode = True.
    """
    pos_id = position.get('id')
    try:
        supabase.table(table_name).update({
            'recovery_cycles':          result['recovery_cycles'],
            'lowest_price_in_recovery': result['new_lowest'],
        }).eq('id', pos_id).execute()
    except Exception as e:
        log_error(MODULE, f'Error actualizando ciclo MR: {e}')

    # Update local dict
    position['recovery_cycles']          = result['recovery_cycles']
    position['lowest_price_in_recovery'] = result['new_lowest']


def finalize_recovery_exit_sync(
    position:      dict,
    result:        dict,
    current_price: float,
    symbol:        str,
    supabase,
    table_name:    str = 'positions',
):
    """
    Registra el resultado de la salida del Modo Recuperación en DB.
    La función de cierre real es llamada por el caller (cada mercado tiene la suya).
    """
    pos_id    = position.get('id')
    exit_type = result['exit_type']
    pnl_pips  = result['pnl_pips']

    try:
        supabase.table(table_name).update({
            'recovery_exit_price':      current_price,
            'recovery_exit_reason':     exit_type,
            'recovery_pnl_pips':        pnl_pips,
            'lowest_price_in_recovery': result.get('new_lowest', 0),
            'recovery_cycles':          result['recovery_cycles'],
        }).eq('id', pos_id).execute()
    except Exception as e:
        log_error(MODULE, f'Error finalizando MR: {e}')

    emoji_map = {
        'trailing_gain': '🟢',
        'zero_loss':     '✅',
        'min_loss':      '🟡',
        'timeout':       '🔴',
    }
    emoji = emoji_map.get(exit_type, '⚪')

    log_info(MODULE,
        f'{emoji} MR SALIDA [{symbol}]: '
        f'{exit_type} | {pnl_pips:.1f} pips | {result["reason"]}'
    )

    _send_telegram_alert(
        f'{emoji} SALIDA RECUPERACIÓN [{symbol}]\n'
        f'Tipo: {exit_type}\n'
        f'P&L: {pnl_pips:+.1f} pips\n'
        f'Ciclos en MR: {result["recovery_cycles"]}\n'
        f'Razón: {result["reason"]}'
    )


# ════════════════════════════════════════════
# ACTUALIZAR SLV CUANDO CAMBIAN LAS BANDAS
# ════════════════════════════════════════════

def update_slv_from_bands_sync(
    position:      dict,
    snap:          dict,
    symbol:        str,
    market_type:   str,
    supabase,
    table_name:    str = 'positions',
):
    """
    El SLV se recalcula cuando las bandas Fibonacci se actualizan.
    Regla: el SLV NUNCA retrocede. Solo mejora (sube para LONG, baja para SHORT).
    En Modo Recuperación NO se mueve el SLV.
    """
    if position.get('recovery_mode'):
        return

    side        = str(position.get('side', 'long')).lower()
    pos_id      = position.get('id')
    entry       = float(
        position.get('avg_entry_price') or
        position.get('entry_price') or
        position.get('avg_price') or 0
    )
    current_slv = float(position.get('slv_price', 0) or 0)

    if current_slv <= 0:
        return  # SLV not yet set

    new_slv_data = calculate_slv(entry, side, symbol, snap, market_type)
    new_slv = new_slv_data['slv_price']

    # SLV NUNCA retrocede
    if side in ('long', 'buy'):
        if new_slv <= current_slv:
            return
    else:
        if new_slv >= current_slv:
            return

    try:
        supabase.table(table_name).update({
            'slv_price': new_slv
        }).eq('id', pos_id).execute()

        position['slv_price'] = new_slv

        log_info(MODULE,
            f'{symbol}: SLV actualizado {current_slv:.6f} → {new_slv:.6f}'
        )
    except Exception as e:
        log_error(MODULE, f'Error actualizando SLV: {e}')


# ════════════════════════════════════════════
# HELPER: Telegram
# ════════════════════════════════════════════

def _send_telegram_alert(message: str):
    """Best-effort Telegram notification."""
    try:
        import asyncio
        from app.workers.alerts_service import send_telegram_message
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(send_telegram_message(message))
        except RuntimeError:
            asyncio.run(send_telegram_message(message))
    except Exception:
        pass
