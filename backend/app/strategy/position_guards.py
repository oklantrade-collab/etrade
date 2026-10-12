"""
ANTIGRAVITY · Position Guards v1.0
===================================
4 correcciones basadas en análisis real de datos de producción.

  #1: Time-Based SL — Evita posiciones zombi (BTC 8 días abierto → -$17.44)
  #2: Max 1 posición por símbolo + cooldown post-SL (evita ×3 BTC SHORTs)
  #3: Anti-spam por símbolo (evita 27 SLs de ADA en <1h)
  #4: Peak PnL tracking (alimenta #1 y mejora análisis)
"""

from datetime import datetime, timezone
from app.core.logger import log_info, log_warning

MODULE = "POSITION_GUARDS"

# ═══════════════════════════════════════════════════════════════════════
#  CORRECCIÓN 1 — Time-Based SL
# ═══════════════════════════════════════════════════════════════════════

TIME_BASED_SL_CONFIG = {
    'crypto_futures': {
        'debil':     {'max_hours': 96,  'min_profit_to_extend': 0.003},
        'moderado':  {'max_hours': 48,  'min_profit_to_extend': 0.005},
        'agresivo':  {'max_hours': 24,  'min_profit_to_extend': 0.008},
        'explosivo': {'max_hours': 12,  'min_profit_to_extend': 0.010},
    },
    'forex_futures': {
        'debil':     {'max_hours': 72,  'min_profit_to_extend': 0.003},
        'moderado':  {'max_hours': 48,  'min_profit_to_extend': 0.005},
        'agresivo':  {'max_hours': 24,  'min_profit_to_extend': 0.008},
        'explosivo': {'max_hours': 12,  'min_profit_to_extend': 0.010},
    },
    'stocks_spot': {
        'debil':     {'max_hours': 240, 'min_profit_to_extend': 0.003},
        'moderado':  {'max_hours': 120, 'min_profit_to_extend': 0.005},
        'agresivo':  {'max_hours': 72,  'min_profit_to_extend': 0.008},
        'explosivo': {'max_hours': 48,  'min_profit_to_extend': 0.010},
    },
}


def check_time_based_sl(position: dict, snap: dict = None) -> dict:
    """
    Evalúa si la posición debe cerrarse por exceder el tiempo máximo
    sin haber alcanzado ganancia mínima.

    Returns:
        dict con 'should_close', 'reason', 'hours_open', 'peak_pnl'
    """
    opened_at = position.get('opened_at')
    if not opened_at:
        return {'should_close': False}

    now = datetime.now(timezone.utc)
    if isinstance(opened_at, str):
        try:
            opened_at = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
        except Exception:
            return {'should_close': False}

    hours_open = (now - opened_at).total_seconds() / 3600

    # Obtener velocidad del mercado desde el snapshot
    velocity = str((snap or {}).get('adx_velocity', 'moderado')).lower()
    if velocity not in ('debil', 'moderado', 'agresivo', 'explosivo'):
        velocity = 'moderado'

    market_type = position.get('market_type', 'crypto_futures')
    cfg = TIME_BASED_SL_CONFIG.get(market_type, {}).get(
        velocity, {'max_hours': 48, 'min_profit_to_extend': 0.005}
    ).copy()

    # Para estrategias swing, triplicar el tiempo máximo permitido (e.g. 12h -> 36h) para permitir maduración
    rule_code = str(position.get('rule_code') or position.get('rule_entry') or '').lower()
    is_swing = any(x in rule_code for x in ['_4h', '_1d', '31a', '31b', '41'])
    if is_swing:
        cfg['max_hours'] = cfg['max_hours'] * 3

    max_hours = cfg['max_hours']
    min_profit_ext = cfg.get('min_profit_to_extend', 0.005)

    if hours_open < max_hours:
        return {'should_close': False, 'hours_open': hours_open, 'max_hours': max_hours}

    # Llegamos al tiempo máximo — verificar si alguna vez estuvo en ganancia
    peak_pnl = float(position.get('peak_pnl_pct', 0))

    if peak_pnl < min_profit_ext * 100:
        # NUNCA estuvo en ganancia significativa → cerrar
        return {
            'should_close': True,
            'reason': f'time_sl_{velocity}',
            'hours_open': round(hours_open, 1),
            'max_hours': max_hours,
            'peak_pnl': round(peak_pnl, 4),
            'velocity': velocity,
            'detail': (
                f'🕐 TIME-BASED SL: {hours_open:.1f}h abierta '
                f'sin ganancia significativa (peak={peak_pnl:.3f}%, '
                f'mínimo={min_profit_ext*100:.1f}%). '
                f'Velocidad: {velocity}, Máx: {max_hours}h'
            )
        }
    else:
        # Sí tuvo ganancia → el trailing debería manejarlo, solo alertar
        log_info(MODULE,
            f'⏰ [{position.get("symbol")}] {hours_open:.1f}h '
            f'(peak={peak_pnl:.3f}%) — trailing activo, no cerrar aún'
        )
        return {'should_close': False, 'hours_open': hours_open, 'peak_pnl': peak_pnl}


# ═══════════════════════════════════════════════════════════════════════
#  CORRECCIÓN 2 — Max 1 posición por símbolo + Cooldown post-SL
# ═══════════════════════════════════════════════════════════════════════

# Registro en memoria de cooldowns activos {symbol_key: datetime}
SL_COOLDOWN_REGISTRY: dict = {}

POST_SL_COOLDOWN = {
    'crypto_futures': {
        'mismo_simbolo':   3.0, # 3 horas (180 minutos)
        'misma_direccion': 3.0, # 3 horas
    },
    'forex_futures': {
        'mismo_simbolo':   3.0, # 3 horas (180 minutos)
        'misma_direccion': 3.0,
    },
    'stocks_spot': {
        'mismo_simbolo':   24,
        'misma_direccion': 48,
    },
}


def is_symbol_in_sl_cooldown(
    symbol: str,
    cooldown_minutes: float = 180.0,
    market_type: str = 'crypto_futures',
    sb = None,
    current_time: datetime = None,
    is_macro_extreme: bool = False,
) -> tuple[bool, float]:
    """
    Verifica si un símbolo está en enfriamiento tras un Stop Loss o Invalidación.
    Si is_macro_extreme es True (UPPER_6 / LOWER_6 macro), el cooldown se anula.
    Retorna (en_cooldown: bool, minutos_restantes: float).
    """
    if is_macro_extreme:
        return False, 0.0
    now = current_time or datetime.now(timezone.utc)
    clean_sym = symbol.replace('/', '').replace('_', '').upper()

    # 1. Comprobación en memoria
    last_sl = SL_COOLDOWN_REGISTRY.get(f'{clean_sym}_any')
    if not last_sl:
        last_sl = SL_COOLDOWN_REGISTRY.get(f'{symbol.upper()}_any')

    if last_sl:
        mins_since = (now - last_sl).total_seconds() / 60.0
        if mins_since < cooldown_minutes:
            return True, round(cooldown_minutes - mins_since, 1)

    # 2. Persistencia en DB (si el worker se reinició y la memoria está vacía)
    if sb is not None:
        try:
            is_forex = any(x in clean_sym for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF')) or market_type == 'forex_futures'
            tbl = 'forex_positions' if is_forex else 'positions'
            res = sb.table(tbl).select('closed_at,exit_reason,status,total_pnl,unrealized_pnl')\
                .eq('symbol', symbol)\
                .eq('status', 'closed')\
                .order('closed_at', desc=True)\
                .limit(1)\
                .execute()
            if res.data and len(res.data) > 0:
                last_pos = res.data[0]
                closed_at_str = last_pos.get('closed_at')
                reason = str(last_pos.get('exit_reason') or '').lower()
                pnl = float(last_pos.get('total_pnl') or last_pos.get('unrealized_pnl') or 0.0)

                sl_triggers = ('sl', 'stop_loss', 'invalidation', 'cut_and_flip')
                is_loss_exit = any(r in reason for r in sl_triggers) or pnl < 0

                if closed_at_str and is_loss_exit:
                    dt_closed = datetime.fromisoformat(closed_at_str.replace('Z', '+00:00'))
                    mins_since_db = (now - dt_closed).total_seconds() / 60.0
                    if mins_since_db < cooldown_minutes:
                        SL_COOLDOWN_REGISTRY[f'{clean_sym}_any'] = dt_closed
                        SL_COOLDOWN_REGISTRY[f'{symbol.upper()}_any'] = dt_closed
                        return True, round(cooldown_minutes - mins_since_db, 1)
        except Exception:
            pass

    return False, 0.0


DAILY_SL_REGISTRY: dict = {}

def can_open_position(
    symbol:         str,
    direction:      str,
    market_type:    str = 'crypto_futures',
    open_positions: list = None,
    is_macro_extreme: bool = False,
) -> dict:
    """
    Verifica si se puede abrir una nueva posición.

    REGLA 1: Solo 1 posición abierta por símbolo (evita ×3 SHORTs).
    REGLA 1B: Límite de Monedas Activas Simultáneas.
    REGLA 2: Cooldown post-SL del mismo símbolo (3 horas).
    REGLA 3: Cooldown de dirección específica (no repetir SHORT fallido).
    REGLA 4: Circuit Breaker Diario (máx 2 SLs por símbolo / día).

    Si is_macro_extreme es True (UPPER_6 / LOWER_6 macro), las reglas 2, 3 y 4 se anulan.

    Returns:
        dict con 'allowed' (bool) y 'reason' (str)
    """
    direction_l = direction.lower()

    # ── REGLA 1: Límite por símbolo (Multi-layer support) ──
    if open_positions:
        from app.core.crypto_symbols import normalize_crypto_symbol
        norm_symbol = normalize_crypto_symbol(symbol)
        
        from app.core.supabase_client import get_risk_config
        try:
            max_per_symbol = int(get_risk_config().get('max_positions_per_symbol', 3))
        except:
            max_per_symbol = 3

        count = 0
        for pos in open_positions:
            if normalize_crypto_symbol(pos.get('symbol', '')) == norm_symbol:
                count += 1
        
        if count >= max_per_symbol:
            return {
                'allowed': False,
                'reason': (
                    f'{symbol}: ya tiene {count} posiciones abiertas '
                    f'→ límite alcanzado (máx {max_per_symbol} por símbolo)'
                )
            }

    # ── REGLA 1B: Límite de Monedas Activas Simultáneas ──
    try:
        from app.core.supabase_client import get_supabase
        sb = get_supabase()
        
        if open_positions is not None:
            active_symbols = set(p.get('symbol') for p in open_positions if p.get('status', 'open') == 'open' and p.get('symbol'))
        else:
            tbl = 'forex_positions' if market_type == 'forex_futures' else 'positions'
            open_res = sb.table(tbl).select('symbol').eq('status', 'open').execute()
            active_symbols = set(p['symbol'] for p in (open_res.data or []))
        
        tc_res = sb.table('trading_config').select('regime_params').eq('id', 1).maybe_single().execute()
        tc_data = tc_res.data if tc_res and tc_res.data else {}
        reg_params = tc_data.get('regime_params', {}) or {}
        
        if market_type in ('crypto_futures', 'crypto_spot'):
            max_active = int(reg_params.get('max_active_symbols_crypto', 1))
        else:
            max_active = int(reg_params.get('max_active_symbols_forex', 1))
            
        if symbol not in active_symbols and len(active_symbols) >= max_active:
            return {
                'allowed': False,
                'reason': f"Cant. Monedas Activas alcanzado ({len(active_symbols)}/{max_active} activas: {list(active_symbols)})"
            }

        if len(active_symbols) > max_active:
            return {
                'allowed': False,
                'reason': f"Cant. Monedas Activas excedido ({len(active_symbols)}/{max_active} activas: {list(active_symbols)})"
            }
    except Exception as max_sym_err:
        pass

    # Si es una oportunidad Macro Extrema (UPPER_6 / LOWER_6), levantar cooldowns y circuit breaker de símbolo
    if is_macro_extreme:
        return {'allowed': True, 'reason': 'Bypass de Zona Extrema Macro (UPPER_6 / LOWER_6) activado'}

    # ── REGLA 4: Circuit Breaker Diario por Símbolo (Máx 2 SLs / día) ──
    now = datetime.now(timezone.utc)
    today_key = now.strftime('%Y-%m-%d')
    clean_sym = symbol.replace('/', '').replace('_', '').upper()
    sym_daily_sls = DAILY_SL_REGISTRY.get(f"{today_key}_{clean_sym}", 0)
    if sym_daily_sls >= 2:
        return {
            'allowed': False,
            'reason': f'{symbol}: Circuit Breaker Diario activo ({sym_daily_sls} SLs hoy >= 2). Símbolo bloqueado hasta mañana.'
        }

    global_daily_sls = DAILY_SL_REGISTRY.get(f"{today_key}_GLOBAL", 0)
    if global_daily_sls >= 3:
        return {
            'allowed': False,
            'reason': f'Circuit Breaker Global de Cuenta activo ({global_daily_sls} SLs globales hoy >= 3). Pausa hasta mañana.'
        }

    # ── REGLA 2: Cooldown general del símbolo post-SL (3 horas) ──
    cfg = POST_SL_COOLDOWN.get(market_type, {})

    last_sl = SL_COOLDOWN_REGISTRY.get(f'{symbol.upper()}_any')
    if last_sl:
        hours_since = (now - last_sl).total_seconds() / 3600
        cooldown = cfg.get('mismo_simbolo', 3.0)
        if hours_since < cooldown:
            remaining = cooldown - hours_since
            return {
                'allowed': False,
                'reason': (
                    f'{symbol}: cooldown post-SL activo '
                    f'({remaining:.1f}h restantes de {cooldown}h)'
                )
            }

    # ── REGLA 3: Cooldown de dirección específica (3 horas) ──
    last_sl_dir = SL_COOLDOWN_REGISTRY.get(f'{symbol.upper()}_{direction_l}')
    if last_sl_dir:
        hours_since = (now - last_sl_dir).total_seconds() / 3600
        cooldown_dir = cfg.get('misma_direccion', 3.0)
        if hours_since < cooldown_dir:
            remaining = cooldown_dir - hours_since
            return {
                'allowed': False,
                'reason': (
                    f'{symbol}/{direction_l}: cooldown dirección activo '
                    f'({remaining:.1f}h restantes de {cooldown_dir}h)'
                )
            }

    return {'allowed': True, 'reason': 'OK'}


def register_sl_event(symbol: str, direction: str, event_time: datetime = None):
    """
    Registra que se activó un SL para este símbolo/dirección.
    Inicia el período de cooldown y actualiza el contador diario.
    """
    now = event_time or datetime.now(timezone.utc)
    clean_sym = symbol.replace('/', '').replace('_', '').upper()
    key_any = f'{clean_sym}_any'
    key_dir = f'{clean_sym}_{direction.lower()}'
    SL_COOLDOWN_REGISTRY[key_any] = now
    SL_COOLDOWN_REGISTRY[key_dir] = now
    SL_COOLDOWN_REGISTRY[f'{symbol.upper()}_any'] = now
    SL_COOLDOWN_REGISTRY[f'{symbol.upper()}_{direction.lower()}'] = now

    today_key = now.strftime('%Y-%m-%d')
    sym_k = f"{today_key}_{clean_sym}"
    DAILY_SL_REGISTRY[sym_k] = DAILY_SL_REGISTRY.get(sym_k, 0) + 1
    DAILY_SL_REGISTRY[f"{today_key}_GLOBAL"] = DAILY_SL_REGISTRY.get(f"{today_key}_GLOBAL", 0) + 1
    log_info(MODULE, f"🛡️ Registrado evento SL para {symbol} ({direction.upper()}). Total hoy para {clean_sym}: {DAILY_SL_REGISTRY[sym_k]}, Global: {DAILY_SL_REGISTRY[f'{today_key}_GLOBAL']}")
    log_info(MODULE,
        f'🧊 COOLDOWN registrado: {symbol}/{direction} → '
        f'SL activado, cooldown iniciado'
    )


# ═══════════════════════════════════════════════════════════════════════
#  CORRECCIÓN 3 — Anti-spam de señales (ADA 27 SLs en <1h)
# ═══════════════════════════════════════════════════════════════════════

# Intervalo mínimo entre señales del mismo símbolo+dirección (minutos)
MIN_SIGNAL_INTERVAL = {
    'BTCUSDT':  60,    # 1 hora mínimo
    'ETHUSDT':  60,
    'SOLUSDT':  60,
    'ADAUSDT':  120,   # 2 horas para ADA (más volátil, más señales falsas)
    # Forex
    'EURUSD':   30,
    'GBPUSD':   30,
    'USDJPY':   30,
    'XAUUSD':   30,
    'DEFAULT':  60,
}

# Registro de última señal procesada {symbol_direction: datetime}
LAST_SIGNAL_TIME: dict = {}


def check_signal_interval(symbol: str, direction: str) -> dict:
    """
    Verifica que haya pasado suficiente tiempo desde la última señal
    del mismo símbolo en la misma dirección.

    Returns:
        dict con 'allowed' (bool) y 'reason' (str)
    """
    now = datetime.now(timezone.utc)
    key = f'{symbol.upper()}_{direction.upper()}'
    min_mins = MIN_SIGNAL_INTERVAL.get(
        symbol.upper(),
        MIN_SIGNAL_INTERVAL['DEFAULT']
    )

    last = LAST_SIGNAL_TIME.get(key)
    if last:
        mins_since = (now - last).total_seconds() / 60
        if mins_since < min_mins:
            return {
                'allowed': False,
                'reason': (
                    f'⏳ {symbol}/{direction}: señal muy reciente '
                    f'({mins_since:.0f}m < {min_mins}m mínimo)'
                )
            }

    # Registrar esta señal como la más reciente
    LAST_SIGNAL_TIME[key] = now
    return {'allowed': True, 'reason': 'OK'}


# ═══════════════════════════════════════════════════════════════════════
#  CORRECCIÓN 4 — Peak PnL tracking
# ═══════════════════════════════════════════════════════════════════════

def update_peak_pnl(position: dict, current_price: float, supabase, table: str = 'positions') -> float:
    """
    Actualiza el PnL máximo alcanzado durante la vida de la posición.
    Crítico para Time-Based SL y análisis post-deploy.

    Returns:
        El nuevo peak_pnl_pct (o el existente si no cambió)
    """
    entry = float(position.get('avg_entry_price') or position.get('entry_price') or 0)
    side = str(position.get('side', 'long')).lower()
    pos_id = str(position.get('id', ''))

    if entry <= 0 or not pos_id:
        return 0.0

    is_long = side in ('long', 'buy')
    if is_long:
        pnl_pct = (current_price - entry) / entry * 100
    else:
        pnl_pct = (entry - current_price) / entry * 100

    current_peak = float(position.get('peak_pnl_pct', 0))

    if pnl_pct > current_peak:
        try:
            supabase.table(table).update({
                'peak_pnl_pct': round(pnl_pct, 4)
            }).eq('id', pos_id).execute()
        except Exception:
            pass  # Non-critical
        return pnl_pct

    return current_peak
