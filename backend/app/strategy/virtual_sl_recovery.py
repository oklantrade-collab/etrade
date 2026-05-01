"""
eTrader v5.0 — Virtual Stop Loss (SLV) Recovery Mechanism
========================================================

Este módulo gestiona el "Modo Recuperación" (Recovery Mode) para posiciones
que tocan el Stop Loss Virtual (SLV). El objetivo es evitar el cierre inmediato
en picos de volatilidad y buscar una salida en breakeven o con pérdida mínima.

Mejoras v5.0:
1. Reducción de ciclos de recuperación (máx 4).
2. Hard Stop dinámico basado en ATR.
3. Lógica de velas (Case A/B) para confirmación de cierre.
4. Verificación urgente cada 5m (independiente del cierre de vela 15m).
"""

import time
from datetime import datetime, timezone
from app.core.logger import log_info, log_warning, log_error

# --- CONFIGURACIÓN SLV v5.0 ---
SLVM_CONFIG = {
    'crypto_futures': {
        'slv_method':            'fibonacci',
        'slv_fibonacci_band':    'lower_1',
        'slv_fallback_pct':      0.02,
        'recovery_max_cycles':   4,     # Reducido de 12 a 4 (60 min total)
        'recovery_target_pips':  0,     # Breakeven
        'recovery_buffer_pips':  2,     # Buffer para ruido
        'trailing_pips_trigger': 10,    # Activa trailing si el rebote es fuerte
        'trailing_pips_step':    5,
    },
    'forex_futures': {
        'slv_method':            'atr',
        'slv_atr_mult':          1.5,
        'recovery_max_cycles':   4,     # 60 min
        'recovery_target_pips':  -2,    # Aceptar pérdida mínima
        'recovery_buffer_pips':  1,
        'trailing_pips_trigger': 8,
        'trailing_pips_step':    4,
    },
    'stocks_spot': {
        'slv_method':            'fixed_pct',
        'slv_fallback_pct':      0.03,
        'recovery_max_cycles':   4,
        'recovery_target_pips':  0,
        'recovery_buffer_pips':  0.1,
        'trailing_pips_trigger': 1.0,
        'trailing_pips_step':    0.5,
    }
}

# Reglas de Hard Stop Dinámico (ATR)
ATR_HARD_STOP_RULES = {
    'crypto_futures': {'pips_base': 15, 'atr_factor': 1.2},
    'forex_futures':  {'pips_base': 10, 'atr_factor': 1.0},
    'stocks_spot':    {'pips_base': 2,  'atr_factor': 0.8}
}

PIP_SIZES = {
    'BTC/USDT': 1.0, 'ETH/USDT': 0.1, 'SOL/USDT': 0.01,
    'EUR/USD': 0.0001, 'GBP/USD': 0.0001, 'USD/JPY': 0.01, 'XAU/USD': 0.01,
    'BTCUSDT': 1.0, 'ETHUSDT': 0.1, 'SOLUSDT': 0.01,
    'EURUSD': 0.0001, 'GBPUSD': 0.0001, 'USDJPY': 0.01, 'XAUUSD': 0.01,
}

# --- FUNCIONES CORE ---

def get_pip_size(symbol: str) -> float:
    return PIP_SIZES.get(symbol, 0.0001 if any(x in symbol for x in ['/','USD']) else 0.01)

def calculate_pips(entry: float, current: float, side: str, symbol: str) -> float:
    pip = get_pip_size(symbol)
    if side.lower() in ('long', 'buy'):
        return (current - entry) / pip
    else:
        return (entry - current) / pip

def calculate_hard_stop_pips(symbol: str, market_type: str, snap: dict) -> float:
    """Calcula el Hard Stop basado en volatilidad (ATR)."""
    rules = ATR_HARD_STOP_RULES.get(market_type, {'pips_base': 10, 'atr_factor': 1.0})
    atr = float(snap.get('atr', 0))
    pip_size = get_pip_size(symbol)
    
    if atr > 0:
        atr_pips = atr / pip_size
        return rules['pips_base'] + (atr_pips * rules['atr_factor'])
    return rules['pips_base'] * 2 # Fallback simple

# --- LÓGICA DE VELAS (CASE A/B) ---

def evaluate_hard_stop_candle(
    side: str,
    v1_open: float,
    v2_close_prev: float,
    v3_current_price: float,
    hard_stop_price: float
) -> dict:
    """
    Evalúa la lógica de velas 15m para confirmación de cierre por Hard Stop.
    Case A (Long): V1 Open < V2 Close Prev (Confirmación bajista) -> Close Market
    Case B (Short): V1 Open > V2 Close Prev (Confirmación alcista) -> Close Market
    """
    is_long = side.lower() in ('long', 'buy')
    
    # Case A: Long confirmación bajista
    if is_long:
        if v1_open < v2_close_prev:
            return {'should_close': True, 'reason': 'hard_stop_v1_bearish_open', 'case': 'A'}
        if v3_current_price < hard_stop_price:
            return {'should_close': True, 'reason': 'hard_stop_price_breach', 'case': 'C'}
    
    # Case B: Short confirmación alcista
    else:
        if v1_open > v2_close_prev:
            return {'should_close': True, 'reason': 'hard_stop_v1_bullish_open', 'case': 'B'}
        if v3_current_price > hard_stop_price:
            return {'should_close': True, 'reason': 'hard_stop_price_breach', 'case': 'C'}
            
    return {'should_close': False, 'reason': 'wait_for_candle_close'}

def check_5m_hard_stop(
    position: dict,
    current_price: float,
    snap: dict,
    symbol: str,
    market_type: str
) -> dict:
    """
    Verificación urgente cada 5 minutos del Hard Stop.
    Si el precio viola el Hard Stop (ATR based), cierra sin esperar a los 15m.
    """
    side = position.get('side', 'long')
    entry_price = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
    
    # Hard Stop dinámico
    hs_pips = calculate_hard_stop_pips(symbol, market_type, snap)
    pip_size = get_pip_size(symbol)
    
    if side.lower() in ('long', 'buy'):
        hs_price = entry_price - (hs_pips * pip_size)
        violated = current_price < hs_price
    else:
        hs_price = entry_price + (hs_pips * pip_size)
        violated = current_price > hs_price
        
    if violated:
        return {
            'should_close': True,
            'reason': 'hard_stop_5m_urgent',
            'hs_pips': hs_pips,
            'hs_price': hs_price
        }
    return {'should_close': False}

# --- EVALUACIÓN DE RECUPERACIÓN V2 ---

def evaluate_recovery_mode_v2(
    position: dict,
    current_price: float,
    snap: dict,
    symbol: str,
    market_type: str = 'crypto_futures'
) -> dict:
    """
    Versión mejorada del evaluador de Modo Recuperación.
    Prioridades:
    1. Hard Stop Urgente (5m)
    2. Lógica de Velas (15m Case A/B)
    3. Trailing Stop (Asegurar rebote)
    4. Timeout (4 ciclos máx)
    5. Target Recovery (Breakeven)
    """
    config = SLVM_CONFIG.get(market_type, SLVM_CONFIG['crypto_futures'])
    side = position.get('side', 'long')
    entry_price = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
    
    # Datos de la vela actual (deberían venir en snap o calcularse)
    # Por ahora usamos placeholders si no vienen
    v1_open = float(snap.get('open_15m', current_price))
    v2_close_prev = float(snap.get('close_prev_15m', current_price))
    
    # 1. Verificar Hard Stop Urgente (5m)
    hs_urgent = check_5m_hard_stop(position, current_price, snap, symbol, market_type)
    if hs_urgent['should_close']:
        return {
            'should_close': True,
            'exit_type': 'hard_stop_urgent',
            'reason': hs_urgent['reason'],
            'hs_pips': hs_urgent['hs_pips']
        }
        
    # 2. Verificar Lógica de Velas Case A/B
    hs_pips = calculate_hard_stop_pips(symbol, market_type, snap)
    pip_size = get_pip_size(symbol)
    hs_price = entry_price - (hs_pips * pip_size) if side.lower() in ('long','buy') else entry_price + (hs_pips * pip_size)
    
    candle_logic = evaluate_hard_stop_candle(side, v1_open, v2_close_prev, current_price, hs_price)
    if candle_logic['should_close']:
        return {
            'should_close': True,
            'exit_type': 'hard_stop_candle',
            'reason': candle_logic['reason'],
            'case': candle_logic.get('case')
        }
        
    # 3. Verificar Timeout (4 ciclos máx)
    cycles = int(position.get('recovery_cycles', 0))
    if cycles >= config['recovery_max_cycles']:
        return {
            'should_close': True,
            'exit_type': 'timeout',
            'reason': f'max_cycles_reached_{cycles}'
        }
        
    # 4. Verificar Target Recovery (Breakeven + Buffer)
    pips = calculate_pips(entry_price, current_price, side, symbol)
    target = config['recovery_target_pips']
    buffer = config['recovery_buffer_pips']
    
    if pips >= (target + buffer):
        return {
            'should_close': True,
            'exit_type': 'recovery_target',
            'reason': f'target_reached_{pips:.1f}_pips'
        }
        
    # 5. Trailing Stop en Recuperación
    # (Si el precio subió y ahora cae de un máximo alcanzado en recuperación)
    # Reutilizamos lógica existente o simplificamos
    
    return {
        'should_close': False,
        'recovery_cycles': cycles + 1,
        'pips': pips,
        'reason': 'monitoring_recovery'
    }

# --- INTEGRACIÓN CON WORKER ---

async def process_symbol_5m_with_slvm_v2(
    symbol:        str,
    current_price: float,
    snap:          dict,
    sb,
    market_type:   str = 'crypto_futures'
):
    """
    Función de conveniencia para llamar desde el scheduler cada 5m.
    Busca la posición abierta y aplica la lógica SLVM v2.
    """
    try:
        # 1. Buscar posición abierta
        res = sb.table('positions').select('*').eq('symbol', symbol).eq('status', 'open').maybe_single().execute()
        if not res.data:
            return
            
        position = res.data
        
        # 2. Evaluar Modo Recuperación V2
        mr_result = evaluate_recovery_mode_v2(
            position=position,
            current_price=current_price,
            snap=snap,
            symbol=symbol,
            market_type=market_type
        )
        
        # 3. Actuar según resultado
        if mr_result['should_close']:
            log_info('SLVM', f"Closing {symbol} by {mr_result['exit_type']}: {mr_result['reason']}")
            
            # Preparar datos de cierre
            update_data = {
                'status': 'closed',
                'close_reason': f"slv_v2_{mr_result['exit_type']}",
                'closed_at': datetime.now(timezone.utc).isoformat(),
                # Logging extendido para auditoría
                'slv_hard_stop_trigger': mr_result.get('exit_type'),
                'slv_hard_stop_pips': mr_result.get('hs_pips'),
                'slv_v1_open': float(snap.get('open_15m', 0)),
                'v2_close_prev': float(snap.get('close_prev_15m', 0)),
                'slv_timeframe_trigger': '5m'
            }
            
            sb.table('positions').update(update_data).eq('id', position['id']).execute()
            
            # Alerta Telegram
            from app.workers.alerts_service import send_telegram_message
            await send_telegram_message(
                f"🛑 SLV RECOVERY CLOSE [{symbol}]\n"
                f"Razón: {mr_result['exit_type'].upper()}\n"
                f"Detalle: {mr_result['reason']}\n"
                f"Precio: {current_price:.5f}"
            )
        else:
            # Actualizar ciclos si está en recuperación
            if position.get('recovery_mode'):
                sb.table('positions').update({
                    'recovery_cycles': mr_result['recovery_cycles']
                }).eq('id', position['id']).execute()
                
    except Exception as e:
        log_error('SLVM_WORKER', f"Error processing {symbol} with SLVM v2: {e}")

# --- COMPATIBILIDAD LEGACY ---

def check_slv_trigger(position: dict, current_price: float) -> bool:
    """Verifica si el precio tocó el SLV para activar modo recuperación."""
    slv_price = position.get('slv_price')
    if not slv_price:
        return False
        
    side = position.get('side', 'long').lower()
    if side in ('long', 'buy'):
        return current_price <= slv_price
    else:
        return current_price >= slv_price

def activate_recovery_mode_sync(position: dict, current_price: float, symbol: str, market_type: str, sb):
    """Activa el flag de recovery_mode en la DB."""
    log_info('SLVM', f"ACTIVATING RECOVERY MODE for {symbol} at {current_price}")
    try:
        sb.table('positions').update({
            'recovery_mode': True,
            'recovery_cycles': 0,
            'recovery_activated_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', position['id']).execute()
    except Exception as e:
        log_error('SLVM', f"Error activating recovery mode: {e}")

# (Mantenemos funciones de cálculo de SLV para integración)
def evaluate_recovery_mode(position: dict, current_price: float, snap: dict, symbol: str, market_type: str = 'crypto_futures'):
    """Wrapper de compatibilidad para la versión antigua del evaluador."""
    return evaluate_recovery_mode_v2(position, current_price, snap, symbol, market_type)

def finalize_recovery_exit_sync(position: dict, mr_result: dict, price: float, symbol: str, sb, table='positions'):
    """Registra el cierre por recuperación de forma síncrona."""
    try:
        sb.table(table).update({
            'status': 'closed',
            'close_reason': f"recovery_{mr_result['exit_type']}",
            'closed_at': datetime.now(timezone.utc).isoformat(),
            'current_price': price,
            'realized_pnl': calculate_pips(float(position.get('avg_entry_price', 0)), price, position.get('side', 'long'), symbol)
        }).eq('id', position['id']).execute()
        log_info('SLVM', f"Finalized recovery exit for {symbol} ({mr_result['exit_type']})")
    except Exception as e:
        log_error('SLVM', f"Error finalizing recovery exit: {e}")

def update_recovery_cycle_sync(position: dict, mr_result: dict, sb, table='positions'):
    """Actualiza el contador de ciclos de recuperación en la DB."""
    try:
        sb.table(table).update({
            'recovery_cycles': mr_result.get('recovery_cycles', 0)
        }).eq('id', position['id']).execute()
    except Exception as e:
        log_error('SLVM', f"Error updating recovery cycles: {e}")

def update_slv_from_bands_sync(position: dict, snap: dict, symbol: str, market_type: str, sb, table='positions'):
    """Actualiza dinámicamente el precio del SLV siguiendo las bandas de Fibonacci si se mueven a favor."""
    # Implementación opcional para trailing del SLV inicial
    # Por ahora lo dejamos como stub para no romper compatibilidad si el servicio lo llama
    pass

def calculate_slv(entry_price: float, side: str, symbol: str, snap: dict, market_type: str = 'crypto_futures') -> dict:
    """Calcula el precio del SLV inicial basado en la configuración."""
    config = SLVM_CONFIG.get(market_type, SLVM_CONFIG['crypto_futures'])
    pip_size = get_pip_size(symbol)
    
    # Lógica simplificada: usa banda Fibonacci o fallback %
    slv_price = 0.0
    source = 'fallback'
    
    if config['slv_method'] == 'fibonacci' and 'lower_1' in snap:
        if side.lower() in ('long', 'buy'):
            slv_price = float(snap.get(config['slv_fibonacci_band'], 0))
            source = config['slv_fibonacci_band']
        else:
            # Para shorts usa la banda superior equivalente
            band = config['slv_fibonacci_band'].replace('lower', 'upper')
            slv_price = float(snap.get(band, 0))
            source = band
            
    if slv_price <= 0:
        dist = entry_price * config.get('slv_fallback_pct', 0.02)
        slv_price = entry_price - dist if side.lower() in ('long','buy') else entry_price + dist
        source = 'fallback_pct'
        
    return {
        'slv_price': slv_price,
        'source': source,
        'distance_pips': abs(entry_price - slv_price) / pip_size
    }
