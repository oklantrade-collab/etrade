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
    )

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
        'mismo_simbolo':   4,   # horas
        'misma_direccion': 8,   # no repetir dirección fallida
    },
    'forex_futures': {
        'mismo_simbolo':   2,
        'misma_direccion': 4,
    },
    'stocks_spot': {
        'mismo_simbolo':   24,
        'misma_direccion': 48,
    },
}


def can_open_position(
    symbol:         str,
    direction:      str,
    market_type:    str = 'crypto_futures',
    open_positions: list = None,
) -> dict:
    """
    Verifica si se puede abrir una nueva posición.

    REGLA 1: Solo 1 posición abierta por símbolo (evita ×3 SHORTs).
    REGLA 2: Cooldown post-SL del mismo símbolo.
    REGLA 3: Cooldown de dirección específica (no repetir SHORT fallido).

    Returns:
        dict con 'allowed' (bool) y 'reason' (str)
    """
    direction_l = direction.lower()

    # ── REGLA 1: Límite por símbolo (Multi-layer support) ──
    if open_positions:
        from app.core.crypto_symbols import normalize_crypto_symbol
        norm_symbol = normalize_crypto_symbol(symbol)
        
        # Obtenemos el límite de la configuración o usamos 4 por defecto
        from app.core.supabase_client import get_risk_config
        try:
            max_per_symbol = int(get_risk_config().get('max_positions_per_symbol', 4))
        except:
            max_per_symbol = 4

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

    # ── REGLA 2: Cooldown general del símbolo post-SL ──
    now = datetime.now(timezone.utc)
    cfg = POST_SL_COOLDOWN.get(market_type, {})

    last_sl = SL_COOLDOWN_REGISTRY.get(f'{symbol.upper()}_any')
    if last_sl:
        hours_since = (now - last_sl).total_seconds() / 3600
        cooldown = cfg.get('mismo_simbolo', 4)
        if hours_since < cooldown:
            remaining = cooldown - hours_since
            return {
                'allowed': False,
                'reason': (
                    f'{symbol}: cooldown post-SL activo '
                    f'({remaining:.1f}h restantes de {cooldown}h)'
                )
            }

    # ── REGLA 3: Cooldown de dirección específica ──
    last_sl_dir = SL_COOLDOWN_REGISTRY.get(f'{symbol.upper()}_{direction_l}')
    if last_sl_dir:
        hours_since = (now - last_sl_dir).total_seconds() / 3600
        cooldown_dir = cfg.get('misma_direccion', 8)
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


def register_sl_event(symbol: str, direction: str):
    """
    Registra que se activó un SL para este símbolo/dirección.
    Inicia el período de cooldown.
    """
    now = datetime.now(timezone.utc)
    key_any = f'{symbol.upper()}_any'
    key_dir = f'{symbol.upper()}_{direction.lower()}'
    SL_COOLDOWN_REGISTRY[key_any] = now
    SL_COOLDOWN_REGISTRY[key_dir] = now
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
