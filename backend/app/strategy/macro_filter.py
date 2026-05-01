"""
Filtro de Contexto Macro — eTrader v5.0

Crypto: BTC es el SPY de las altcoins.
  Si BTC cae → no comprar altcoins.
  Si BTC sube → condiciones favorables.

Forex: DXY es la brújula del dólar.
  DXY fuerte → no ir largo en pares USD/XXX.
  DXY débil  → oportunidades en EUR, GBP, etc.
"""

import pandas as pd
from app.core.logger import log_info
from app.core.memory_store import MEMORY_STORE

# ── Configuración ──────────────────────────────
MACRO_FILTER_CONFIG = {
    'crypto': {
        'btc_drop_warn':    -2.0,  # % en 4H
        'btc_drop_danger':  -4.0,  # % en 4H
        'btc_rise_confirm':  1.5,  # % en 4H
        'btc_atr_extreme':   5.0,  # % del precio
        'btc_rvol_fear':     3.0,  # > 3x = pánico
    },
    'forex': {
        'dxy_strong':      104.0,
        'dxy_very_strong': 107.0,
        'dxy_weak':        100.0,
        'usd_positive_pairs': [
            'USDJPY', 'USDCHF', 'USDCAD'
        ],
        'usd_negative_pairs': [
            'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD'
        ],
    },
}


def get_btc_macro_context(
    btc_snap:  dict,
    btc_df_4h: pd.DataFrame = None,
) -> dict:
    """
    Calcula el contexto macro de BTC para filtrar
    entradas en altcoins.

    Retorna:
      sentiment:   'bullish'|'neutral'|'bearish'
      allow_long:  bool
      allow_short: bool
      score:       -10 a +10
      reason:      str
    """
    cfg   = MACRO_FILTER_CONFIG['crypto']
    score = 0.0
    flags = []

    btc_price = float(btc_snap.get('price', 0) or 0)
    btc_basis = float(btc_snap.get('basis', 0) or 0)

    # ── BTC cambio en 4H ──────────────────────
    btc_change_4h = 0.0
    if btc_df_4h is not None and len(btc_df_4h) >= 2:
        close_now  = float(
            btc_df_4h.iloc[-1].get('close', 0)
        )
        close_prev = float(
            btc_df_4h.iloc[-2].get('close', 0)
        )
        if close_prev > 0:
            btc_change_4h = (
                close_now - close_prev
            ) / close_prev * 100

    if btc_change_4h <= cfg['btc_drop_danger']:
        score -= 4
        flags.append(
            f'BTC colapsando ({btc_change_4h:.1f}% en 4H)'
        )
    elif btc_change_4h <= cfg['btc_drop_warn']:
        score -= 2
        flags.append(
            f'BTC cayendo ({btc_change_4h:.1f}% en 4H)'
        )
    elif btc_change_4h >= cfg['btc_rise_confirm']:
        score += 2
        flags.append(
            f'BTC alcista (+{btc_change_4h:.1f}% en 4H)'
        )

    # ── SAR y MTF de BTC ─────────────────────
    btc_sar = int(btc_snap.get('sar_trend_4h', 0) or 0)
    btc_mtf = float(btc_snap.get('mtf_score', 0) or 0)

    if btc_sar < 0:
        score -= 2
        flags.append('BTC SAR bajista')
    elif btc_sar > 0:
        score += 2
        flags.append('BTC SAR alcista')

    if btc_mtf < -0.3:
        score -= 1
        flags.append(f'BTC MTF débil ({btc_mtf:.2f})')
    elif btc_mtf > 0.3:
        score += 1
        flags.append(f'BTC MTF fuerte (+{btc_mtf:.2f})')

    # ── RVOL pánico ───────────────────────────
    btc_rvol = float(btc_snap.get('rvol', 1.0) or 1.0)
    if btc_rvol >= cfg['btc_rvol_fear'] and \
       btc_change_4h < 0:
        score -= 2
        flags.append(
            f'BTC: RVOL pánico ({btc_rvol:.1f}x en caída)'
        )

    score = max(-10.0, min(10.0, score))

    if score >= 2:
        sentiment   = 'bullish'
        allow_long  = True
        allow_short = False
    elif score <= -2:
        sentiment   = 'bearish'
        allow_long  = False
        allow_short = True
    else:
        sentiment   = 'neutral'
        allow_long  = True
        allow_short = True

    return {
        'sentiment':     sentiment,
        'score':         score,
        'btc_change_4h': round(btc_change_4h, 2),
        'btc_sar':       btc_sar,
        'btc_mtf':       btc_mtf,
        'allow_long':    allow_long,
        'allow_short':   allow_short,
        'flags':         flags,
        'reduce_sizing': abs(score) >= 3,
        'reason': (
            f'BTC macro: {sentiment} '
            f'(score={score:.0f}/10). '
            + ', '.join(flags)
        ),
    }


def get_dxy_forex_context(
    dxy_price:  float,
    dxy_change: float = 0.0,
    symbol:     str   = 'EURUSD',
) -> dict:
    """
    Filtra entradas en Forex según el DXY.

    DXY fuerte + EURUSD → no comprar, sí vender
    DXY débil  + EURUSD → sí comprar, no vender
    DXY fuerte + USDJPY → sí comprar, no vender
    """
    cfg          = MACRO_FILTER_CONFIG['forex']
    score        = 0.0
    flags        = []
    usd_positive = cfg['usd_positive_pairs']
    usd_negative = cfg['usd_negative_pairs']

    if dxy_price >= cfg['dxy_very_strong']:
        score   = 4
        dxy_env = 'very_strong'
        flags.append(f'DXY muy fuerte ({dxy_price:.1f})')
    elif dxy_price >= cfg['dxy_strong']:
        score   = 2
        dxy_env = 'strong'
        flags.append(f'DXY fuerte ({dxy_price:.1f})')
    elif dxy_price <= cfg['dxy_weak']:
        score   = -2
        dxy_env = 'weak'
        flags.append(f'DXY débil ({dxy_price:.1f})')
    else:
        score   = 0
        dxy_env = 'neutral'

    if dxy_change >= 0.5:
        score += 1
        flags.append(f'DXY subiendo +{dxy_change:.2f}%')
    elif dxy_change <= -0.5:
        score -= 1
        flags.append(f'DXY cayendo {dxy_change:.2f}%')

    if symbol in usd_positive:
        allow_long  = score >= 0
        allow_short = score <= 0
        bias = 'long' if score > 0 \
               else 'short' if score < 0 \
               else 'neutral'
    elif symbol in usd_negative:
        allow_long  = score <= 0
        allow_short = score >= 0
        bias = 'short' if score > 0 \
               else 'long' if score < 0 \
               else 'neutral'
    else:
        allow_long  = True
        allow_short = True
        bias        = 'neutral'

    return {
        'dxy_price':   dxy_price,
        'dxy_env':     dxy_env,
        'dxy_score':   score,
        'symbol':      symbol,
        'bias':        bias,
        'allow_long':  allow_long,
        'allow_short': allow_short,
        'flags':       flags,
        'reason': (
            f'DXY {dxy_env} ({dxy_price:.1f}): '
            f'bias={bias} para {symbol}. '
            + ', '.join(flags)
        ),
    }


async def fetch_macro_context(
    market_type: str,
    symbol:      str,
    supabase,
) -> dict:
    """
    Obtiene contexto macro completo desde Supabase.
    Para Crypto: usa BTC de market_snapshot.
    Para Forex: usa DXY de market_snapshot.
    """
    if market_type == 'crypto_futures':
        btc_res = await supabase \
            .table('market_snapshot') \
            .select('*') \
            .eq('symbol', 'BTCUSDT') \
            .maybe_single() \
            .execute()
        btc_snap  = btc_res.data or {}
        btc_df_4h = MEMORY_STORE.get(
            'BTCUSDT', {}
        ).get('4h', {}).get('df')

        macro = get_btc_macro_context(btc_snap, btc_df_4h)
        macro['market_type'] = 'crypto'
        return macro

    else:  # forex
        dxy_res = await supabase \
            .table('market_snapshot') \
            .select('price,basis_slope_pct') \
            .eq('symbol', 'DXY') \
            .maybe_single() \
            .execute()
        dxy_data   = dxy_res.data or {}
        dxy_price  = float(dxy_data.get('price', 102.0) or 102.0)
        dxy_change = float(
            dxy_data.get('basis_slope_pct', 0) or 0
        )

        macro = get_dxy_forex_context(
            dxy_price, dxy_change, symbol
        )
        macro['market_type'] = 'forex'
        return macro
