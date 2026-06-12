"""
Filtro de Contexto Macro — eTrader v6.0

Crypto:
  - Estrategias Aa/Bb seleccionadas: EMA50 vs EMA200 en 5m
  - Circuit Breaker: Si BTC detecta spike bajista, bloquear LONGs globalmente
  - Demás estrategias: sin restricciones macro

Forex:
  - DXY dinámico: usa EMA50 vs EMA200 de EURUSD como proxy inverso
  - Fallback a umbrales estáticos si no hay datos disponibles
"""

import pandas as pd
from app.core.logger import log_info, log_warning
from app.core.memory_store import MEMORY_STORE, MARKET_SNAPSHOT_CACHE

# ── Configuración ──────────────────────────────
MACRO_FILTER_CONFIG = {
    'crypto': {
        # Circuit Breaker: umbrales de pánico BTC
        'circuit_breaker_enabled': True,
        'btc_spike_block_longs':   True,   # Si BTC spike down → bloquear LONGs
    },
    'forex': {
        # Fallback estáticos (solo si no hay EMAs disponibles)
        'dxy_strong':      104.0,
        'dxy_very_strong': 107.0,
        'dxy_weak':        100.0,
        'usd_positive_pairs': [
            'USDJPY', 'USDCHF', 'USDCAD'
        ],
        'usd_negative_pairs': [
            'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD'
        ],
        # Mejora C: Límite de correlación USD
        'max_same_usd_direction': 2,  # Máximo 2 posiciones en la misma dirección USD
    },
}

# ── Estrategias sujetas al filtro EMA 5m ──
EMA_FILTERED_RULES = [
    "aa21", "aa21_5m", "aa25", "aa23", "aahot",
    "bb21", "bb25", "bb23", "bbhot"
]

# ── Grupos de correlación USD ──
USD_CORRELATION_GROUPS = {
    'pro_usd': {
        # Operaciones que se benefician de un USD fuerte
        'EURUSD':  'short',
        'GBPUSD':  'short',
        'AUDUSD':  'short',
        'NZDUSD':  'short',
        'USDJPY':  'long',
        'USDCHF':  'long',
        'USDCAD':  'long',
    },
    'anti_usd': {
        # Operaciones que se benefician de un USD débil
        'EURUSD':  'long',
        'GBPUSD':  'long',
        'AUDUSD':  'long',
        'NZDUSD':  'long',
        'USDJPY':  'short',
        'USDCHF':  'short',
        'USDCAD':  'short',
    },
}


# ══════════════════════════════════════════════════
#  MEJORA B: Circuit Breaker BTC (Crypto)
# ══════════════════════════════════════════════════

def check_btc_circuit_breaker() -> dict:
    """
    Verifica si BTC está en estado de pánico (spike bajista).
    Si se detecta un spike con dirección 'down', bloquea todos
    los LONGs de altcoins inmediatamente.

    Retorna:
        block_longs:  bool  → True si hay pánico
        block_shorts: bool  → siempre False (en pánico se permite shortear)
        reason:       str
    """
    cfg = MACRO_FILTER_CONFIG['crypto']
    if not cfg.get('circuit_breaker_enabled', True):
        return {'block_longs': False, 'block_shorts': False, 'reason': 'Circuit Breaker desactivado'}

    btc_snap = MARKET_SNAPSHOT_CACHE.get('BTCUSDT', {})
    if not btc_snap:
        return {'block_longs': False, 'block_shorts': False, 'reason': 'Sin datos BTC'}

    spike_detected = btc_snap.get('spike_detected', False)
    spike_direction = str(btc_snap.get('spike_direction', '')).lower()
    spike_ratio = float(btc_snap.get('spike_ratio', 0) or 0)

    if spike_detected and spike_direction in ('down', 'bearish', 'sell'):
        reason = (
            f"⚠️ CIRCUIT BREAKER: BTC spike bajista detectado "
            f"(ratio={spike_ratio:.1f}x). LONGs bloqueados globalmente."
        )
        log_warning('CIRCUIT_BREAKER', reason)
        return {
            'block_longs':  True,
            'block_shorts': False,
            'reason':       reason,
        }

    return {'block_longs': False, 'block_shorts': False, 'reason': 'BTC estable'}


# ══════════════════════════════════════════════════
#  MEJORA A: DXY Dinámico (Forex)
# ══════════════════════════════════════════════════

def get_dxy_forex_context(
    dxy_price:  float,
    dxy_change: float = 0.0,
    symbol:     str   = 'EURUSD',
    eurusd_df:  pd.DataFrame = None,
) -> dict:
    """
    Filtra entradas en Forex según la fuerza del USD.

    MEJORA A: Usa EMA50 vs EMA200 de EURUSD como proxy dinámico del DXY.
    Si EURUSD EMA50 > EMA200 → USD débil (EURUSD sube = dólar cae)
    Si EURUSD EMA50 < EMA200 → USD fuerte (EURUSD baja = dólar sube)

    Fallback: umbrales estáticos si no hay datos de EURUSD.
    """
    cfg          = MACRO_FILTER_CONFIG['forex']
    score        = 0.0
    flags        = []
    usd_positive = cfg['usd_positive_pairs']
    usd_negative = cfg['usd_negative_pairs']
    use_dynamic  = False

    # ── Intentar EMA dinámica de EURUSD ──────────
    if eurusd_df is not None and len(eurusd_df) >= 200:
        ema50  = eurusd_df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        ema200 = eurusd_df['close'].ewm(span=200, adjust=False).mean().iloc[-1]
        use_dynamic = True

        if ema50 < ema200:
            # EURUSD cayendo → USD fuerte
            diff_pct = (ema200 - ema50) / ema200 * 100
            if diff_pct > 0.5:
                score   = 4
                dxy_env = 'very_strong'
                flags.append(f'USD muy fuerte (EURUSD EMA50 {ema50:.5f} << EMA200 {ema200:.5f})')
            else:
                score   = 2
                dxy_env = 'strong'
                flags.append(f'USD fuerte (EURUSD EMA50 {ema50:.5f} < EMA200 {ema200:.5f})')
        elif ema50 > ema200:
            # EURUSD subiendo → USD débil
            diff_pct = (ema50 - ema200) / ema200 * 100
            if diff_pct > 0.5:
                score   = -4
                dxy_env = 'very_weak'
                flags.append(f'USD muy débil (EURUSD EMA50 {ema50:.5f} >> EMA200 {ema200:.5f})')
            else:
                score   = -2
                dxy_env = 'weak'
                flags.append(f'USD débil (EURUSD EMA50 {ema50:.5f} > EMA200 {ema200:.5f})')
        else:
            score   = 0
            dxy_env = 'neutral'
            flags.append('USD neutral (EMA50 ≈ EMA200)')
    else:
        # ── Fallback: umbrales estáticos del DXY ──
        if dxy_price >= cfg['dxy_very_strong']:
            score   = 4
            dxy_env = 'very_strong'
            flags.append(f'DXY muy fuerte ({dxy_price:.1f}) [estático]')
        elif dxy_price >= cfg['dxy_strong']:
            score   = 2
            dxy_env = 'strong'
            flags.append(f'DXY fuerte ({dxy_price:.1f}) [estático]')
        elif dxy_price <= cfg['dxy_weak']:
            score   = -2
            dxy_env = 'weak'
            flags.append(f'DXY débil ({dxy_price:.1f}) [estático]')
        else:
            score   = 0
            dxy_env = 'neutral'

    # Momentum adicional (slope)
    if dxy_change >= 0.5:
        score += 1
        flags.append(f'DXY subiendo +{dxy_change:.2f}%')
    elif dxy_change <= -0.5:
        score -= 1
        flags.append(f'DXY cayendo {dxy_change:.2f}%')

    # ── Determinar allow_long / allow_short según par ──
    if symbol in usd_positive:
        # Pares como USDJPY: USD fuerte → long favorable
        allow_long  = score >= 0
        allow_short = score <= 0
        bias = 'long' if score > 0 \
               else 'short' if score < 0 \
               else 'neutral'
    elif symbol in usd_negative:
        # Pares como EURUSD: USD fuerte → short favorable
        allow_long  = score <= 0
        allow_short = score >= 0
        bias = 'short' if score > 0 \
               else 'long' if score < 0 \
               else 'neutral'
    else:
        allow_long  = True
        allow_short = True
        bias        = 'neutral'

    method = 'EMA dinámica' if use_dynamic else 'estático'
    return {
        'dxy_price':   dxy_price,
        'dxy_env':     dxy_env,
        'dxy_score':   score,
        'symbol':      symbol,
        'bias':        bias,
        'allow_long':  allow_long,
        'allow_short': allow_short,
        'flags':       flags,
        'method':      method,
        'reason': (
            f'USD {dxy_env} ({method}): '
            f'bias={bias} para {symbol}. '
            + ', '.join(flags)
        ),
    }


# ══════════════════════════════════════════════════
#  MEJORA C: Filtro de Correlación USD (Forex)
# ══════════════════════════════════════════════════

def check_usd_exposure_filter(
    symbol:     str,
    direction:  str,
    open_forex_positions: list,
) -> dict:
    """
    Verifica la exposición acumulada al USD antes de abrir
    una nueva posición de Forex.

    Agrupa las posiciones abiertas por su dirección respecto al USD:
      - Pro-USD: SHORT EURUSD, LONG USDJPY, etc.
      - Anti-USD: LONG EURUSD, SHORT USDJPY, etc.

    Si ya hay 2+ posiciones en la misma dirección USD que la nueva
    operación, bloquea la entrada para evitar sobre-exposición.

    Retorna:
        passed:  bool
        reason:  str or None
        pro_usd_count:  int
        anti_usd_count: int
    """
    max_same = MACRO_FILTER_CONFIG['forex'].get('max_same_usd_direction', 2)
    pro_usd  = USD_CORRELATION_GROUPS['pro_usd']
    anti_usd = USD_CORRELATION_GROUPS['anti_usd']

    # Clasificar la nueva operación
    new_is_pro_usd  = pro_usd.get(symbol, '').lower() == direction.lower()
    new_is_anti_usd = anti_usd.get(symbol, '').lower() == direction.lower()

    # Si el par no tiene correlación USD conocida, permitir
    if not new_is_pro_usd and not new_is_anti_usd:
        return {
            'passed': True,
            'reason': None,
            'pro_usd_count': 0,
            'anti_usd_count': 0,
        }

    # Contar exposiciones existentes
    pro_usd_count  = 0
    anti_usd_count = 0

    for pos in open_forex_positions:
        pos_symbol = pos.get('symbol', '')
        pos_side   = (pos.get('side') or pos.get('direction') or '').lower()

        if pro_usd.get(pos_symbol, '').lower() == pos_side:
            pro_usd_count += 1
        elif anti_usd.get(pos_symbol, '').lower() == pos_side:
            anti_usd_count += 1

    # Evaluar si excede el límite
    if new_is_pro_usd and pro_usd_count >= max_same:
        return {
            'passed': False,
            'reason': (
                f"Límite correlación USD alcanzado: ya hay {pro_usd_count} posiciones Pro-USD "
                f"(máx {max_same}). No abrir {direction.upper()} {symbol}."
            ),
            'pro_usd_count':  pro_usd_count,
            'anti_usd_count': anti_usd_count,
        }

    if new_is_anti_usd and anti_usd_count >= max_same:
        return {
            'passed': False,
            'reason': (
                f"Límite correlación USD alcanzado: ya hay {anti_usd_count} posiciones Anti-USD "
                f"(máx {max_same}). No abrir {direction.upper()} {symbol}."
            ),
            'pro_usd_count':  pro_usd_count,
            'anti_usd_count': anti_usd_count,
        }

    return {
        'passed': True,
        'reason': None,
        'pro_usd_count':  pro_usd_count,
        'anti_usd_count': anti_usd_count,
    }


# ══════════════════════════════════════════════════
#  ENTRY POINT: fetch_macro_context
# ══════════════════════════════════════════════════

async def fetch_macro_context(
    market_type: str,
    symbol:      str,
    supabase,
    rule_code:   str = None,
    df_5m:       pd.DataFrame = None
) -> dict:
    """
    Obtiene contexto macro completo.

    Crypto:
      1. Circuit Breaker BTC (spike bajista → bloquear LONGs global)
      2. EMA50 vs EMA200 en 5m para estrategias Aa/Bb seleccionadas
      3. Demás estrategias: sin restricciones macro

    Forex:
      1. DXY dinámico (EMA50 vs EMA200 de EURUSD como proxy inverso)
      2. Fallback a umbrales estáticos si no hay datos
    """
    if market_type == 'crypto_futures':
        # ── MEJORA B: Circuit Breaker BTC ──────────
        cb = check_btc_circuit_breaker()
        if cb['block_longs'] or cb['block_shorts']:
            return {
                'sentiment':    'panic',
                'score':        -10,
                'allow_long':   not cb['block_longs'],
                'allow_short':  not cb['block_shorts'],
                'flags':        [cb['reason']],
                'reduce_sizing': True,
                'reason':       cb['reason'],
                'market_type':  'crypto',
            }

        # ── Filtro EMA 5m para estrategias seleccionadas ──
        rc = rule_code.strip().lower() if rule_code else ""

        if rc in EMA_FILTERED_RULES:
            if df_5m is not None and len(df_5m) >= 200:
                ema50  = df_5m['close'].ewm(span=50, adjust=False).mean().iloc[-1]
                ema200 = df_5m['close'].ewm(span=200, adjust=False).mean().iloc[-1]

                if ema50 > ema200:
                    allow_long  = True
                    allow_short = False
                    reason = (
                        f"EMA50 ({ema50:.2f}) > EMA200 ({ema200:.2f}) en 5m "
                        f"-> Solo LONGs permitidos para {rc.upper()}"
                    )
                elif ema50 < ema200:
                    allow_long  = False
                    allow_short = True
                    reason = (
                        f"EMA50 ({ema50:.2f}) < EMA200 ({ema200:.2f}) en 5m "
                        f"-> Solo SHORTs permitidos para {rc.upper()}"
                    )
                else:
                    allow_long  = True
                    allow_short = True
                    reason = f"EMA50 == EMA200 en 5m -> Neutral para {rc.upper()}"

                return {
                    'sentiment':    'bullish' if ema50 > ema200 else 'bearish',
                    'score':        10 if ema50 > ema200 else -10,
                    'allow_long':   allow_long,
                    'allow_short':  allow_short,
                    'flags':        [reason],
                    'reduce_sizing': False,
                    'reason':       reason,
                    'market_type':  'crypto',
                }
            else:
                return {
                    'sentiment':    'neutral',
                    'score':        0,
                    'allow_long':   True,
                    'allow_short':  True,
                    'flags':        ["Sin suficientes datos 5m para evaluar EMA"],
                    'reduce_sizing': False,
                    'reason':       f"Sin datos 5m para evaluar regla EMA en {rc.upper()}",
                    'market_type':  'crypto',
                }
        else:
            # Las demás estrategias manejan su propia dinámica
            return {
                'sentiment':    'neutral',
                'score':        0,
                'allow_long':   True,
                'allow_short':  True,
                'flags':        ["Regla macro EMA no aplicable"],
                'reduce_sizing': False,
                'reason':       f"Estrategia {rc.upper() if rc else 'N/A'} maneja su propia dinámica",
                'market_type':  'crypto',
            }

    else:  # forex
        # ── MEJORA A: DXY Dinámico ──────────────
        # Obtener precio DXY de snapshot (si existe)
        dxy_price  = 102.0
        dxy_change = 0.0
        try:
            dxy_res = supabase \
                .table('market_snapshot') \
                .select('price,basis_slope_pct') \
                .eq('symbol', 'DXY') \
                .maybe_single() \
                .execute()
            dxy_data   = dxy_res.data or {}
            dxy_price  = float(dxy_data.get('price', 102.0) or 102.0)
            dxy_change = float(dxy_data.get('basis_slope_pct', 0) or 0)
        except Exception:
            pass

        # Obtener EURUSD DataFrame de 15m para proxy dinámico
        eurusd_df = MEMORY_STORE.get('EURUSD', {}).get('15m', {}).get('df')

        macro = get_dxy_forex_context(
            dxy_price, dxy_change, symbol,
            eurusd_df=eurusd_df,
        )
        macro['market_type'] = 'forex'
        return macro
