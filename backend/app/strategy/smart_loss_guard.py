"""
Smart Anti-Loss Guard v2.0 — eTrader
=====================================

Protege posiciones en pérdida SOLO cuando la tendencia macro es favorable.
Cuando la tendencia se rompe (EMA20 < EMA50 para LONGs), permite el cierre.

Aplica para Crypto y Forex.
"""

from app.core.logger import log_info, log_warning

MODULE = "SMART_GUARD"

# ── Razones de cierre EXENTAS (siempre se permite el cierre) ──
EXEMPT_KEYWORDS = [
    'tp',              # Take Profit
    'erep',            # Cierre del propio EREP
    'manual',          # Orden del usuario
    'trailing',        # Trailing stop
    'ts_close',        # Trailing stop close
    'emergency',       # Emergencia ws_manager
    'hard_cap',        # Hard cap protection
    'sharp_drop',      # Sharp drop protection
    'apexconfluence',  # Apex confluence signal
    'cleanup',         # Limpieza administrativa
]


def is_exempt_reason(reason: str) -> bool:
    """
    Verifica si la razón de cierre está exenta del guard.
    Estas razones SIEMPRE se permiten sin evaluación de tendencia.
    """
    reason_lower = str(reason).lower()
    
    # tp_band ya no es exento para que pueda ser bloqueado por el Guard
    # si está en pérdida y la tendencia macro aún nos favorece.
    if 'tp_band' in reason_lower:
        return False
        
    # Validar 'tp' exacto o prefijos conocidos para verdaderos Take Profits
    if reason_lower == 'tp' or reason_lower.startswith('tp_hit'):
        return True
        
    # Filtrar 'tp' de la lista de keywords generales para evitar colisiones
    general_keywords = [kw for kw in EXEMPT_KEYWORDS if kw != 'tp']
    return any(kw in reason_lower for kw in general_keywords)


def _safe_float(val, default=0.0):
    """Convierte a float de forma segura."""
    try:
        if val is None:
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def evaluate_trend_health(snap: dict, side: str, market_type: str = 'crypto_futures') -> dict:
    """
    Evalúa la salud de la tendencia macro usando EMAs del snapshot de 15m.
    
    Para LONGs:
      - EMA20 > EMA50 > EMA200 → Tendencia alcista sana → Proteger
      - EMA20 > EMA50, EMA50 < EMA200 → Recuperando → Proteger con cautela
      - EMA20 < EMA50 → Tendencia rota → NO proteger
      
    Para SHORTs:
      - EMA20 < EMA50 < EMA200 → Tendencia bajista sana → Proteger
      - EMA20 < EMA50, EMA50 > EMA200 → Recuperando → Proteger con cautela
      - EMA20 > EMA50 → Tendencia rota → NO proteger
    
    Args:
        snap: Snapshot de indicadores (15m)
        side: 'long'/'buy' o 'short'/'sell'
        market_type: 'crypto_futures' o 'forex_futures'
        
    Returns:
        dict con:
          - trend_healthy: bool — ¿La tendencia soporta la posición?
          - guard_active: bool — ¿Debe activarse el guard?
          - confidence: str — 'strong', 'moderate', 'none'
          - ema_alignment: str — Descripción del alineamiento
          - reason: str — Razón legible
    """
    if not snap:
        return {
            'trend_healthy': False,
            'guard_active': False,
            'confidence': 'none',
            'ema_alignment': 'no_data',
            'reason': 'Sin snapshot disponible — no se puede evaluar tendencia',
        }

    # Extraer EMAs del snapshot (compatibilidad con ambos formatos de nombre)
    ema20 = _safe_float(snap.get('ema_20') or snap.get('ema3'))
    ema50 = _safe_float(snap.get('ema_50') or snap.get('ema4'))
    ema200 = _safe_float(snap.get('ema_200') or snap.get('ema5'))

    # Si no tenemos al menos EMA20 y EMA50, no podemos evaluar
    if ema20 <= 0 or ema50 <= 0:
        return {
            'trend_healthy': False,
            'guard_active': False,
            'confidence': 'none',
            'ema_alignment': 'incomplete_data',
            'ema20': ema20,
            'ema50': ema50,
            'ema200': ema200,
            'reason': f'EMAs insuficientes (ema20={ema20}, ema50={ema50}) — guard desactivado',
        }

    is_long = side.lower() in ('long', 'buy')

    if is_long:
        # ── LONGS ──
        if ema20 > ema50:
            if ema200 > 0 and ema50 > ema200:
                # EMA20 > EMA50 > EMA200: tendencia alcista fuerte
                return {
                    'trend_healthy': True,
                    'guard_active': True,
                    'confidence': 'strong',
                    'ema_alignment': 'bullish_aligned',
                    'ema20': ema20,
                    'ema50': ema50,
                    'ema200': ema200,
                    'reason': f'Tendencia ALCISTA sana: EMA20({ema20:.4f}) > EMA50({ema50:.4f}) > EMA200({ema200:.4f})',
                }
            else:
                # EMA20 > EMA50 pero EMA50 < EMA200: recuperando
                return {
                    'trend_healthy': True,
                    'guard_active': True,
                    'confidence': 'moderate',
                    'ema_alignment': 'bullish_recovering',
                    'ema20': ema20,
                    'ema50': ema50,
                    'ema200': ema200,
                    'reason': f'Tendencia recuperando: EMA20({ema20:.4f}) > EMA50({ema50:.4f}), EMA200({ema200:.4f}) aún por encima',
                }
        else:
            # EMA20 < EMA50: tendencia rota para longs
            broken_detail = ''
            if ema200 > 0 and ema50 < ema200:
                broken_detail = ' (EMA50 < EMA200 — bajista total)'
            return {
                'trend_healthy': False,
                'guard_active': False,
                'confidence': 'none',
                'ema_alignment': 'bearish_broken',
                'ema20': ema20,
                'ema50': ema50,
                'ema200': ema200,
                'reason': f'Tendencia ROTA para LONG: EMA20({ema20:.4f}) < EMA50({ema50:.4f}){broken_detail}',
            }
    else:
        # ── SHORTS ──
        if ema20 < ema50:
            if ema200 > 0 and ema50 < ema200:
                # EMA20 < EMA50 < EMA200: tendencia bajista fuerte
                return {
                    'trend_healthy': True,
                    'guard_active': True,
                    'confidence': 'strong',
                    'ema_alignment': 'bearish_aligned',
                    'ema20': ema20,
                    'ema50': ema50,
                    'ema200': ema200,
                    'reason': f'Tendencia BAJISTA sana: EMA20({ema20:.4f}) < EMA50({ema50:.4f}) < EMA200({ema200:.4f})',
                }
            else:
                # EMA20 < EMA50 pero EMA50 > EMA200: recuperando bajista
                return {
                    'trend_healthy': True,
                    'guard_active': True,
                    'confidence': 'moderate',
                    'ema_alignment': 'bearish_recovering',
                    'ema20': ema20,
                    'ema50': ema50,
                    'ema200': ema200,
                    'reason': f'Tendencia bajista recuperando: EMA20({ema20:.4f}) < EMA50({ema50:.4f})',
                }
        else:
            # EMA20 > EMA50: tendencia rota para shorts
            broken_detail = ''
            if ema200 > 0 and ema50 > ema200:
                broken_detail = ' (EMA50 > EMA200 — alcista total)'
            return {
                'trend_healthy': False,
                'guard_active': False,
                'confidence': 'none',
                'ema_alignment': 'bullish_broken',
                'ema20': ema20,
                'ema50': ema50,
                'ema200': ema200,
                'reason': f'Tendencia ROTA para SHORT: EMA20({ema20:.4f}) > EMA50({ema50:.4f}){broken_detail}',
            }


def should_block_close(
    snap: dict,
    side: str,
    reason: str,
    total_pnl: float,
    market_type: str = 'crypto_futures',
    symbol: str = None,
) -> dict:
    """
    Decisión final: ¿debe bloquearse este cierre?
    
    Args:
        snap: Snapshot de indicadores (15m). Puede ser None.
        side: 'long'/'buy' o 'short'/'sell'
        reason: Razón del cierre intentado
        total_pnl: PnL total en USD
        market_type: 'crypto_futures' o 'forex_futures'
        symbol: Símbolo de la posición para consultar timeframes en MEMORY_STORE.
        
    Returns:
        dict con:
          - block: bool — True si se debe BLOQUEAR el cierre
          - reason: str — Razón de la decisión
          - trend: dict — Resultado de evaluate_trend_health()
    """
    # 1. Si PnL es positivo o cero, NO bloquear (cerrar en ganancia siempre OK)
    if total_pnl >= 0:
        return {
            'block': False,
            'reason': f'PnL positivo (${total_pnl:.4f}) — cierre permitido',
            'trend': None,
        }

    # 2. Si la razón está exenta, NO bloquear
    if is_exempt_reason(reason):
        return {
            'block': False,
            'reason': f'Razón exenta ({reason}) — cierre permitido',
            'trend': None,
        }

    # 3. Timeout dinámico: evaluar periodo de 5 minutos (5m)
    if symbol:
        from app.core.memory_store import MEMORY_STORE
        df_5m = MEMORY_STORE.get(symbol, {}).get('5m', {}).get('df')
        if df_5m is not None and not df_5m.empty:
            last_5m = df_5m.iloc[-1]
            ema20_5m = _safe_float(last_5m.get('ema_20') or last_5m.get('ema3'))
            ema50_5m = _safe_float(last_5m.get('ema_50') or last_5m.get('ema4'))
            
            if ema20_5m > 0 and ema50_5m > 0:
                is_long = side.lower() in ('long', 'buy')
                if is_long and ema20_5m < ema50_5m:
                    log_warning(MODULE,
                        f"Smart Guard TIMEOUT (5m): Permitiendo cierre de {symbol} "
                        f"porque tendencia corta se rompió: EMA20_5m({ema20_5m:.4f}) < EMA50_5m({ema50_5m:.4f})"
                    )
                    return {
                        'block': False,
                        'reason': f'Timeout del guard en 5m (EMA20({ema20_5m:.4f}) < EMA50({ema50_5m:.4f})) — cierre permitido',
                        'trend': None,
                    }
                elif not is_long and ema20_5m > ema50_5m:
                    log_warning(MODULE,
                        f"Smart Guard TIMEOUT (5m): Permitiendo cierre de {symbol} "
                        f"porque tendencia corta se rompió: EMA20_5m({ema20_5m:.4f}) > EMA50_5m({ema50_5m:.4f})"
                    )
                    return {
                        'block': False,
                        'reason': f'Timeout del guard en 5m (EMA20({ema20_5m:.4f}) > EMA50({ema50_5m:.4f})) — cierre permitido',
                        'trend': None,
                    }

    # 4. Si no hay snapshot, intentar recuperarlo de MEMORY_STORE (15m)
    if not snap and symbol:
        from app.core.memory_store import MEMORY_STORE
        df_15m = MEMORY_STORE.get(symbol, {}).get('15m', {}).get('df')
        if df_15m is not None and not df_15m.empty:
            snap = df_15m.iloc[-1].to_dict()

    if not snap:
        return {
            'block': False,
            'reason': 'Sin snapshot (15m) disponible — cierre permitido por precaución',
            'trend': None,
        }

    # 5. Evaluar tendencia macro (15m)
    trend = evaluate_trend_health(snap, side, market_type)

    if trend['guard_active']:
        # Tendencia sana — BLOQUEAR el cierre
        log_warning(MODULE,
            f"SMART GUARD ACTIVADO: Bloqueando cierre en perdida "
            f"(PnL=${total_pnl:.4f}, reason={reason}). "
            f"Tendencia: {trend['ema_alignment']} ({trend['confidence']}). "
            f"{trend['reason']}"
        )
        return {
            'block': True,
            'reason': trend['reason'],
            'trend': trend,
        }
    else:
        # Tendencia rota — PERMITIR el cierre
        log_info(MODULE,
            f"Smart Guard: tendencia rota, permitiendo cierre "
            f"(PnL=${total_pnl:.4f}, reason={reason}). "
            f"{trend['reason']}"
        )
        return {
            'block': False,
            'reason': trend['reason'],
            'trend': trend,
        }
