"""
eTrader v5.0 -- Virtual Stop Loss (SLV) Recovery Mechanism
========================================================

Este modulo gestiona el "Modo Recuperacion" (Recovery Mode) para posiciones
que tocan el Stop Loss Virtual (SLV). El objetivo es evitar el cierre inmediato
en picos de volatilidad y buscar una salida en breakeven o con perdida minima.

Mejoras v5.0:
1. Reduccion de ciclos de recuperacion (max 4).
2. Hard Stop dinamico basado en ATR.
3. Logica de velas (Case A/B) para confirmacion de cierre.
4. Verificacion urgente cada 5m (independiente del cierre de vela 15m).
"""

import time
from datetime import datetime, timezone
from app.core.logger import log_info, log_warning, log_error

def safe_db_update(sb, table: str, record_id, update_data: dict, key_name: str = 'id'):
    """
    Defensively updates a table row. If PostgREST schema cache throws PGRST204 
    because a column is missing from the database schema, it dynamically 
    removes the missing column from the payload and retries the update.
    """
    current_data = update_data.copy()
    max_attempts = len(update_data) + 1
    
    for attempt in range(max_attempts):
        try:
            res = sb.table(table).update(current_data).eq(key_name, record_id).execute()
            return res
        except Exception as e:
            err_str = str(e)
            is_schema_cache_error = False
            
            # Extract from dict or string exception
            if isinstance(e, dict):
                err_code = e.get('code')
                err_msg = e.get('message', '')
                is_schema_cache_error = (err_code == 'PGRST204' or 'column' in err_msg.lower() or 'schema cache' in err_msg.lower())
                err_str = err_msg + " " + str(e)
            else:
                is_schema_cache_error = ('PGRST204' in err_str or 'column' in err_str.lower() or 'schema cache' in err_str.lower())
                
            if is_schema_cache_error:
                removed = False
                for key in list(current_data.keys()):
                    # Match key inside single/double quotes or directly in the error string
                    if f"'{key}'" in err_str or f'"{key}"' in err_str or f"column {key}" in err_str or key in err_str:
                        current_data.pop(key)
                        log_warning('SLVM_SAFE_DB', f"Dynamically removed missing column '{key}' from update payload on table '{table}' and retrying.")
                        removed = True
                        break
                if not removed:
                    # If we couldn't match a column, raise original error
                    raise e
            else:
                raise e
    raise Exception(f"Failed to update table {table} after removing missing columns.")

def safe_float(v, default=0.0):
    try:
        if v is None: return default
        return float(v)
    except (ValueError, TypeError):
        return default


def safe_int(v, default=0):
    try:
        if v is None: return default
        return int(float(v))
    except (ValueError, TypeError):
        return default

# --- CONFIGURACION SLV v5.0 ---
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
        'slv_method':            'fixed_pips',   # Cambiado de 'atr' (calculaba 275 pips!)
        'slv_fixed_pips':        25,              # SLV a maximo 25 pips del entry
        'slv_atr_mult':          1.5,             # Fallback si se usa ATR
        'recovery_max_cycles':   12,              # 12 minutos maximo en recuperacion
        'recovery_target_pips':  -2,              # Aceptar perdida minima
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

# Reglas de Hard Stop Dinamico (ATR)
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
    if symbol in ('XAUUSD', 'XAU/USD'):
        rules = {'pips_base': 600, 'atr_factor': 1.0}
    elif symbol in ('USDJPY', 'USD/JPY'):
        rules = {'pips_base': 60, 'atr_factor': 1.2}
    elif symbol in ('GBPUSD', 'GBP/USD'):
        rules = {'pips_base': 30, 'atr_factor': 1.1}
    else:
        rules = ATR_HARD_STOP_RULES.get(market_type, {'pips_base': 10, 'atr_factor': 1.0})
    atr = safe_float(snap.get('atr', 0))
    pip_size = get_pip_size(symbol)
    
    if atr > 0:
        atr_pips = atr / pip_size
        return rules['pips_base'] + (atr_pips * rules['atr_factor'])
    return rules['pips_base'] * 2 # Fallback simple

# --- LOGICA DE VELAS (CASE A/B) ---

def evaluate_hard_stop_candle(
    side: str,
    v1_open: float,
    v2_close_prev: float,
    v3_current_price: float,
    hard_stop_price: float
) -> dict:
    """
    Evalua la logica de velas 15m para confirmacion de cierre por Hard Stop.
    Case A (Long): V1 Open < V2 Close Prev (Confirmacion bajista) -> Close Market
    Case B (Short): V1 Open > V2 Close Prev (Confirmacion alcista) -> Close Market
    """
    is_long = side.lower() in ('long', 'buy')
    
    # Case A: Long confirmacion bajista
    if is_long:
        if v1_open < v2_close_prev:
            return {'should_close': True, 'reason': 'hard_stop_v1_bearish_open', 'case': 'A'}
        if v3_current_price < hard_stop_price:
            return {'should_close': True, 'reason': 'hard_stop_price_breach', 'case': 'C'}
    
    # Case B: Short confirmacion alcista
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
    Verificacion urgente cada 5 minutos del Hard Stop.
    Si el precio viola el Hard Stop (ATR based), cierra sin esperar a los 15m.
    """
    side = position.get('side', 'long')
    entry_price = safe_float(position.get('avg_entry_price') or position.get('entry_price') or 0)
    
    # Hard Stop dinamico
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

# --- EVALUACION DE RECUPERACION V2 ---

def evaluate_recovery_mode_v2(
    position: dict,
    current_price: float,
    snap: dict,
    symbol: str,
    market_type: str = 'crypto_futures'
) -> dict:
    """
    Version mejorada del evaluador de Modo Recuperacion.
    Prioridades:
    1. Hard Stop Urgente (5m)
    2. Logica de Velas (15m Case A/B)
    3. Trailing Stop (Asegurar rebote)
    4. Timeout (4 ciclos max)
    5. Target Recovery (Breakeven)
    """
    config = SLVM_CONFIG.get(market_type, SLVM_CONFIG['crypto_futures'])
    side = position.get('side', 'long')
    entry_price = safe_float(position.get('avg_entry_price') or position.get('entry_price') or 0)
    
    # Datos de la vela actual (deberían venir en snap o calcularse)
    # Por ahora usamos placeholders si no vienen
    v1_open = safe_float(snap.get('open_15m', current_price))
    v2_close_prev = safe_float(snap.get('close_prev_15m', current_price))
    
    # 1. Verificar Hard Stop Urgente (5m)
    hs_urgent = check_5m_hard_stop(position, current_price, snap, symbol, market_type)
    if hs_urgent['should_close']:
        return {
            'should_close': True,
            'exit_type': 'hard_stop_urgent',
            'reason': hs_urgent['reason'],
            'hs_pips': hs_urgent['hs_pips']
        }

    # 1.5 Verificar Cruce de EMAs en contra (Corte urgente en Modo Recuperacion)
    ema3 = safe_float(snap.get('ema_3', 0))
    ema9 = safe_float(snap.get('ema_9', 0))
    if ema3 > 0 and ema9 > 0:
        if side.lower() in ('long', 'buy') and ema3 < ema9:
            return {
                'should_close': True,
                'exit_type': 'recovery_ema_contrary_cross',
                'reason': f'EMA3 ({ema3:.5f}) < EMA9 ({ema9:.5f}) en recuperacion'
            }
        elif side.lower() in ('short', 'sell') and ema3 > ema9:
            return {
                'should_close': True,
                'exit_type': 'recovery_ema_contrary_cross',
                'reason': f'EMA3 ({ema3:.5f}) > EMA9 ({ema9:.5f}) en recuperacion'
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
        
    # 3. Verificar Timeout (4 ciclos max)
    cycles = safe_int(position.get('recovery_cycles', 0))
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
    Funcion de conveniencia para llamar desde el scheduler cada 5m.
    Busca la posicion abierta y aplica la logica SLVM v2.
    """
    try:
        table_name = 'forex_positions' if 'forex' in market_type else 'positions'
        
        # 1. Buscar posición abierta
        res = sb.table(table_name).select('*').eq('symbol', symbol).eq('status', 'open').maybe_single().execute()
        if not res or not hasattr(res, 'data') or not res.data:
            return
            
        position = res.data
        
        # 1.5 Si la posición no está en modo recuperación, sólo verificamos si debe activarse
        if not position.get('recovery_mode'):
            if check_slv_trigger(position, current_price):
                activate_recovery_mode_sync(position, current_price, symbol, market_type, sb, table_name)
            return
        
        # 2. Evaluar Modo Recuperación V2 (sólo si ya está activado)
        mr_result = evaluate_recovery_mode_v2(
            position=position,
            current_price=current_price,
            snap=snap,
            symbol=symbol,
            market_type=market_type
        )
        
        # Determine unique key columns for dynamic DB updates
        import uuid
        is_uuid = False
        pos_id = position.get('id')
        if pos_id:
            try:
                uuid.UUID(str(pos_id))
                is_uuid = True
            except ValueError:
                is_uuid = False

        db_key_name = 'id'
        db_record_id = pos_id
        if 'forex' in market_type and not is_uuid:
            db_key_name = 'ctrader_order_id'
            db_record_id = position.get('ctrader_order_id') or pos_id
        
        # 3. Actuar según resultado
        if mr_result['should_close']:
            log_info('SLVM', f"Closing {symbol} by {mr_result['exit_type']}: {mr_result['reason']}")
            
            # Preparar datos de cierre
            update_data = {
                'status': 'closed',
                'close_reason': f"slv_v2_{mr_result['exit_type']}",
                'closed_at': datetime.now(timezone.utc).isoformat(),
                # Logging extendido para auditoria
                'slv_hard_stop_trigger': mr_result.get('exit_type'),
                'slv_hard_stop_pips': mr_result.get('hs_pips'),
                'slv_v1_open': safe_float(snap.get('open_15m', 0)),
                'v2_close_prev': safe_float(snap.get('close_prev_15m', 0)),
                'slv_timeframe_trigger': '5m'
            }
            
            safe_db_update(sb, table_name, db_record_id, update_data, key_name=db_key_name)
            
            # Alerta Telegram
            from app.workers.alerts_service import send_telegram_message
            await send_telegram_message(
                f"STOP SLV RECOVERY CLOSE [{symbol}]\n"
                f"Razon: {mr_result['exit_type'].upper()}\n"
                f"Detalle: {mr_result['reason']}\n"
                f"Precio: {current_price:.5f}"
            )
        else:
            # Actualizar ciclos si está en recuperación
            if position.get('recovery_mode'):
                safe_db_update(sb, table_name, db_record_id, {
                    'recovery_cycles': mr_result['recovery_cycles']
                }, key_name=db_key_name)
                
    except Exception as e:
        log_error('SLVM_WORKER', f"Error processing {symbol} with SLVM v2: {e}")

# --- COMPATIBILIDAD LEGACY ---

def check_slv_trigger(position: dict, current_price: float) -> bool:
    """Verifica si el precio toco el SLV para activar modo recuperacion."""
    slv_price = position.get('slv_price')
    if not slv_price:
        return False
        
    side = position.get('side', 'long').lower()
    if side in ('long', 'buy'):
        return current_price <= slv_price
    else:
        return current_price >= slv_price

def activate_recovery_mode_sync(position: dict, current_price: float, symbol: str, market_type: str, sb, table='positions'):
    """Activa el flag de recovery_mode en la DB."""
    log_info('SLVM', f"ACTIVATING RECOVERY MODE for {symbol} at {current_price} on table {table}")
    try:
        safe_db_update(sb, table, position['id'], {
            'recovery_mode': True,
            'recovery_cycles': 0,
            'recovery_activated_at': datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        log_error('SLVM', f"Error activating recovery mode on table {table}: {e}")

# (Mantenemos funciones de cálculo de SLV para integración)
def evaluate_recovery_mode(position: dict, current_price: float, snap: dict, symbol: str, market_type: str = 'crypto_futures'):
    """Wrapper de compatibilidad para la version antigua del evaluador."""
    return evaluate_recovery_mode_v2(position, current_price, snap, symbol, market_type)

def finalize_recovery_exit_sync(position: dict, mr_result: dict, price: float, symbol: str, sb, table='positions'):
    """Registra el cierre por recuperacion de forma sincrona."""
    try:
        safe_db_update(sb, table, position['id'], {
            'status': 'closed',
            'close_reason': f"recovery_{mr_result['exit_type']}",
            'closed_at': datetime.now(timezone.utc).isoformat(),
            'current_price': price,
            'realized_pnl': calculate_pips(safe_float(position.get('avg_entry_price', 0)), price, position.get('side', 'long'), symbol)
        })
        log_info('SLVM', f"Finalized recovery exit for {symbol} ({mr_result['exit_type']})")
    except Exception as e:
        log_error('SLVM', f"Error finalizing recovery exit: {e}")

def update_recovery_cycle_sync(position: dict, mr_result: dict, sb, table='positions'):
    """Actualiza el contador de ciclos de recuperacion en la DB."""
    try:
        safe_db_update(sb, table, position['id'], {
            'recovery_cycles': mr_result.get('recovery_cycles', 0)
        })
    except Exception as e:
        log_error('SLVM', f"Error updating recovery cycles: {e}")

def update_slv_from_bands_sync(position: dict, snap: dict, symbol: str, market_type: str, sb, table='positions'):
    """Actualiza dinamicamente el precio del SLV siguiendo las bandas de Fibonacci si se mueven a favor."""
    # Implementacion opcional para trailing del SLV inicial
    # Por ahora lo dejamos como stub para no romper compatibilidad si el servicio lo llama
    pass

def calculate_slv(entry_price: float, side: str, symbol: str, snap: dict, market_type: str = 'crypto_futures') -> dict:
    """Calcula el precio del SLV inicial basado en la configuracion."""
    config = SLVM_CONFIG.get(market_type, SLVM_CONFIG['crypto_futures'])
    pip_size = get_pip_size(symbol)
    
    slv_price = 0.0
    source = 'fallback'
    
    # Metodo 1: Pips fijos (recomendado para forex)
    if config['slv_method'] == 'fixed_pips':
        fixed_pips = config.get('slv_fixed_pips', 25)
        if symbol in ('XAUUSD', 'XAU/USD'):
            fixed_pips = 600 # 600 pips ($6.00 USD) para evitar gatillar modo recuperacion prematuro en Oro
        elif symbol in ('USDJPY', 'USD/JPY'):
            fixed_pips = 50  # 50 pips ($0.50 JPY) para evitar gatillar modo recuperacion prematuro en el Yen
        elif symbol in ('GBPUSD', 'GBP/USD'):
            fixed_pips = 35  # 35 pips ($0.0035 USD) para evitar gatillar modo recuperacion prematuro en la Libra
        if side.lower() in ('long', 'buy'):
            slv_price = entry_price - (fixed_pips * pip_size)
        else:
            slv_price = entry_price + (fixed_pips * pip_size)
        source = f'fixed_{fixed_pips}_pips'
    
    # Metodo 2: Fibonacci band
    elif config['slv_method'] == 'fibonacci' and 'lower_1' in snap:
        if side.lower() in ('long', 'buy'):
            slv_price = safe_float(snap.get(config.get('slv_fibonacci_band', 'lower_1'), 0))
            source = config.get('slv_fibonacci_band', 'lower_1')
        else:
            band = config.get('slv_fibonacci_band', 'lower_1').replace('lower', 'upper')
            slv_price = safe_float(snap.get(band, 0))
            source = band
    
    # Metodo 3: ATR-based (con cap de seguridad)
    elif config['slv_method'] == 'atr':
        atr = safe_float(snap.get('atr', 0))
        if atr > 0:
            mult = config.get('slv_atr_mult', 1.5)
            dist = atr * mult
            # CAP: No permitir mas de 30 pips para forex (excepto Oro/Yen/Libra)
            max_dist = 600 * pip_size if symbol in ('XAUUSD', 'XAU/USD') else (50 * pip_size if symbol in ('USDJPY', 'USD/JPY') else (40 * pip_size if symbol in ('GBPUSD', 'GBP/USD') else 30 * pip_size))
            dist = min(dist, max_dist)
            if side.lower() in ('long', 'buy'):
                slv_price = entry_price - dist
            else:
                slv_price = entry_price + dist
            source = f'atr_x{mult}_capped'
    
    # Fallback: Porcentaje fijo
    if slv_price <= 0:
        dist = entry_price * config.get('slv_fallback_pct', 0.02)
        # CAP: No mas de 30 pips (excepto Oro/Yen/Libra)
        max_dist = 600 * pip_size if symbol in ('XAUUSD', 'XAU/USD') else (50 * pip_size if symbol in ('USDJPY', 'USD/JPY') else (40 * pip_size if symbol in ('GBPUSD', 'GBP/USD') else 30 * pip_size))
        dist = min(dist, max_dist)
        slv_price = entry_price - dist if side.lower() in ('long','buy') else entry_price + dist
        source = 'fallback_pct_capped'
        
    return {
        'slv_price': slv_price,
        'source': source,
        'distance_pips': abs(entry_price - slv_price) / pip_size
    }
