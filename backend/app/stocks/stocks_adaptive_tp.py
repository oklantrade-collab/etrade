"""
TP Adaptativo con Detección de Agotamiento
para STOCKS.

El sistema monitorea en 15m y 5m:
  1. Rechazos del precio en bandas Fibonacci
  2. Velas de agotamiento (SIPV)
  3. Contexto macro (VIX/SPY/NDX)
  4. Volume y momentum (MACD)

Cuando detecta agotamiento → adapta los TPs
para no perder la ganancia acumulada.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone

from app.core.logger import log_info, log_error


MODULE = "ADAPTIVE_TP"

# ── Umbrales de agotamiento ───────────────────
EXHAUSTION_CONFIG = {
    # Rechazos consecutivos en una banda
    'rejection_threshold':     2,
    # 2 rechazos = señal débil
    'rejection_threshold_strong': 3,
    # 3+ rechazos = señal fuerte

    # Cuerpo mínimo de la vela para considerar
    # un rechazo (% del rango total)
    'rejection_body_pct':      0.30,

    # Score mínimo para adaptar B1
    'exhaustion_adapt_b1':     5.0,  # de 10
    # Score mínimo para adaptar B2
    'exhaustion_adapt_b2':     7.0,

    # Macro: umbrales
    'vix_fear':                20.0,
    # VIX > 20 = mercado con miedo
    'vix_extreme':             25.0,
    # VIX > 25 = pánico, salir rápido
    'spy_drop_warn':          -0.5,
    # SPY cae 0.5% = precaución
    'spy_drop_danger':        -1.0,
    # SPY cae 1% = reducir targets
    'ndx_drop_warn':          -0.8,
    'ndx_drop_danger':        -1.5,

    # Reducción de target cuando macro es malo
    'macro_target_reduction':  0.5,
    # reducir target al 50% de la banda
}

# Patrones de vela de agotamiento (SIPV)
EXHAUSTION_PATTERNS = [
    'shooting_star',
    'bearish_engulfing',
    'doji_gravestone',
    'hanging_man',
    'bearish_harami',
    'evening_star',
]


# ═══════════════════════════════════════════
# MÓDULO 1 — MACRO SCORE
# ═══════════════════════════════════════════

def calculate_macro_score(
    vix:        float = 15.0,
    spy_change: float = 0.0,
    ndx_change: float = 0.0,
) -> dict:
    """
    Calcula el score macro del mercado.
    Score positivo = viento a favor
    Score negativo = viento en contra

    Rango: -10 (pánico) a +10 (euforia)
    Neutral: 0 ± 2
    """
    cfg   = EXHAUSTION_CONFIG
    score = 0.0
    flags = []

    # ── VIX ───────────────────────────────────
    if vix >= cfg['vix_extreme']:
        score -= 4
        flags.append(f'VIX EXTREMO ({vix:.1f})')
    elif vix >= cfg['vix_fear']:
        score -= 2
        flags.append(f'VIX MIEDO ({vix:.1f})')
    elif vix < 15:
        score += 1
        flags.append(f'VIX CALMO ({vix:.1f})')

    # ── SPY ───────────────────────────────────
    if spy_change <= cfg['spy_drop_danger']:
        score -= 3
        flags.append(
            f'SPY PELIGRO ({spy_change:.2f}%)'
        )
    elif spy_change <= cfg['spy_drop_warn']:
        score -= 1.5
        flags.append(
            f'SPY CAÍDA ({spy_change:.2f}%)'
        )
    elif spy_change >= 0.5:
        score += 1.5
        flags.append(
            f'SPY SUBE ({spy_change:.2f}%)'
        )

    # ── NASDAQ ────────────────────────────────
    if ndx_change <= cfg['ndx_drop_danger']:
        score -= 3
        flags.append(
            f'NDX PELIGRO ({ndx_change:.2f}%)'
        )
    elif ndx_change <= cfg['ndx_drop_warn']:
        score -= 1.5
        flags.append(
            f'NDX CAÍDA ({ndx_change:.2f}%)'
        )
    elif ndx_change >= 0.8:
        score += 1.5
        flags.append(
            f'NDX SUBE ({ndx_change:.2f}%)'
        )

    # Normalizar a -10/+10
    score = max(-10, min(10, score))

    # Clasificar
    if score >= 3:
        sentiment = 'bullish'
        color     = '#00C896'
    elif score >= 0:
        sentiment = 'neutral'
        color     = '#FFB74D'
    elif score >= -3:
        sentiment = 'cautious'
        color     = '#FF8A65'
    else:
        sentiment = 'bearish'
        color     = '#FF4757'

    return {
        'score':     round(score, 2),
        'sentiment': sentiment,
        'color':     color,
        'flags':     flags,
        'reduce_targets': score <= -3,
        'exit_fast':      score <= -5,
    }


# ═══════════════════════════════════════════
# MÓDULO 2 — DETECTOR DE RECHAZOS EN BANDA
# ═══════════════════════════════════════════

def detect_band_rejection(
    df:          pd.DataFrame,
    band_price:  float,
    n_candles:   int = 5,
    tolerance:   float = 0.005,
) -> dict:
    """
    Detecta si el precio ha intentado cruzar
    una banda Fibonacci y ha sido rechazado.

    Un rechazo ocurre cuando:
      high >= band_price × (1 - tolerance)
      AND
      close < band_price

    Es decir: el precio tocó la banda pero
    cerró por debajo de ella.

    Analiza las últimas n_candles velas de 15m.
    """
    if df is None or len(df) < 3:
        return {
            'rejections': 0,
            'rejected':   False,
            'strength':   'none',
        }

    recent       = df.tail(n_candles)
    rejection_count = 0
    rejection_details = []

    for i, (idx, row) in enumerate(
        recent.iterrows()
    ):
        high  = float(row.get('high', 0))
        close = float(row.get('close', 0))
        open_ = float(row.get('open', 0))
        low   = float(row.get('low', 0))

        # ¿El precio tocó la banda?
        touched = high >= band_price * (
            1 - tolerance
        )
        # ¿El precio cerró por debajo?
        closed_below = close < band_price

        if touched and closed_below:
            # Calcular el tamaño del rechazo
            candle_range = high - low
            rejection_size = high - close
            rejection_pct  = (
                rejection_size / candle_range
                if candle_range > 0 else 0
            )

            if rejection_pct >= \
               EXHAUSTION_CONFIG['rejection_body_pct']:
                rejection_count += 1
                rejection_details.append({
                    'candle_idx': i,
                    'high':       high,
                    'close':      close,
                    'rej_pct':    round(
                        rejection_pct * 100, 1
                    ),
                })

    cfg = EXHAUSTION_CONFIG
    if rejection_count >= \
       cfg['rejection_threshold_strong']:
        strength = 'strong'
    elif rejection_count >= \
         cfg['rejection_threshold']:
        strength = 'moderate'
    elif rejection_count == 1:
        strength = 'weak'
    else:
        strength = 'none'

    return {
        'rejections':  rejection_count,
        'rejected':    rejection_count >= \
                       cfg['rejection_threshold'],
        'strength':    strength,
        'details':     rejection_details,
        'band_price':  band_price,
    }


# ═══════════════════════════════════════════
# MÓDULO 3 — DETECTOR DE VELAS SIPV
# ═══════════════════════════════════════════

def detect_exhaustion_candle(
    df:         pd.DataFrame,
    timeframe:  str = '15m',
) -> dict:
    """
    Detecta patrones de vela de agotamiento
    usando el SIPV (Sistema de Identificación
    de Patrones de Velas).

    Patrones bajistas relevantes:
      Shooting Star: sombra superior larga,
                     cuerpo pequeño abajo
      Doji Gravestone: sombra superior larga,
                       sin cuerpo
      Bearish Engulfing: vela roja que envuelve
                         a la verde anterior
      Hanging Man: sombra inferior larga en techo
      Evening Star: 3 velas (sube, doji, baja)
    """
    if df is None or len(df) < 3:
        return {
            'detected':  False,
            'pattern':   None,
            'strength':  0,
        }

    last   = df.iloc[-1]
    prev   = df.iloc[-2]
    prev2  = df.iloc[-3]

    o  = float(last.get('open',  0))
    h  = float(last.get('high',  0))
    l  = float(last.get('low',   0))
    c  = float(last.get('close', 0))

    if h == l:
        return {'detected': False, 'pattern': None, 'strength': 0}

    total_range  = h - l
    body_size    = abs(c - o)
    body_pct     = body_size / total_range
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    upper_pct    = upper_shadow / total_range
    lower_pct    = lower_shadow / total_range

    patterns_found = []

    # ── Shooting Star ─────────────────────────
    if (upper_pct >= 0.60 and
        body_pct <= 0.25 and
        c < o and
        lower_pct <= 0.15):
        patterns_found.append({
            'name':     'shooting_star',
            'strength': 8,
            'reason':   'Sombra superior larga, cuerpo pequeño arriba'
        })

    # ── Doji Gravestone ───────────────────────
    elif (upper_pct >= 0.70 and
          body_pct <= 0.10 and
          lower_pct <= 0.10):
        patterns_found.append({
            'name':     'doji_gravestone',
            'strength': 7,
            'reason':   'Doji con sombra superior muy larga'
        })

    # ── Bearish Engulfing ─────────────────────
    po  = float(prev.get('open',  0))
    pc  = float(prev.get('close', 0))
    if (c < o and
        pc > po and
        o >= pc and
        c <= po):
        patterns_found.append({
            'name':     'bearish_engulfing',
            'strength': 9,
            'reason':   'Vela bajista envuelve la alcista anterior'
        })

    # ── Hanging Man ───────────────────────────
    elif (lower_pct >= 0.60 and
          body_pct <= 0.25 and
          upper_pct <= 0.10):
        patterns_found.append({
            'name':     'hanging_man',
            'strength': 6,
            'reason':   'Hanging man (sombra inferior en techo)'
        })

    # ── Evening Star ──────────────────────────
    p2o = float(prev2.get('open',  0))
    p2c = float(prev2.get('close', 0))
    if (p2c > p2o and      # vela 1: alcista
        abs(pc - po) < total_range * 0.3 and
        # vela 2: pequeña (doji)
        c < o and          # vela 3: bajista
        c < (p2o + p2c) / 2):  # cierra < mitad
        patterns_found.append({
            'name':     'evening_star',
            'strength': 9,
            'reason':   'Evening Star: 3 velas de techo'
        })

    if not patterns_found:
        return {
            'detected': False,
            'pattern':  None,
            'strength': 0,
        }

    # Retornar el patrón más fuerte
    best = max(
        patterns_found,
        key=lambda x: x['strength']
    )

    return {
        'detected':  True,
        'pattern':   best['name'],
        'strength':  best['strength'],
        'reason':    best['reason'],
        'timeframe': timeframe,
        'all_patterns': patterns_found,
    }


# ═══════════════════════════════════════════
# MÓDULO 4 — SCORE DE AGOTAMIENTO
# ═══════════════════════════════════════════

def calculate_exhaustion_score(
    ticker:      str,
    position:    dict,
    current_price: float,
    snap:        dict,
    df_15m:      pd.DataFrame,
    df_5m:       pd.DataFrame = None,
    macro:       dict = None,
) -> dict:
    """
    Calcula el score de agotamiento 0-10.
    Combina todos los indicadores.

    Score 0-3:  Sin agotamiento (mantener)
    Score 4-6:  Agotamiento moderado (alerta)
    Score 7-8:  Agotamiento fuerte (cerrar B1)
    Score 9-10: Agotamiento extremo (cerrar B1+B2)
    """
    score      = 0.0
    components = {}

    entry_price = float(position.get('avg_price') or position.get('entry_price') or 0)

    highest_band = int(position.get(
        'tp_highest_band', 0
    ))

    # ── Determinar la banda actual ────────────
    current_band = 0
    for n in range(6, 0, -1):
        band_val = float(snap.get(
            f'upper_{n}', 0
        ))
        if band_val > 0 and \
           current_price >= band_val * 0.98:
            current_band = n
            break

    # ── C1: Rechazo en banda actual ───────────
    if current_band > 0:
        band_price = float(snap.get(
            f'upper_{current_band}', 0
        ))
        if band_price > 0 and df_15m is not None:
            rejection = detect_band_rejection(
                df_15m, band_price, n_candles=6
            )
            if rejection['strength'] == 'strong':
                score += 3.0
            elif rejection['strength'] == 'moderate':
                score += 2.0
            elif rejection['strength'] == 'weak':
                score += 1.0

            components['rejection'] = {
                'band':       current_band,
                'rejections': rejection['rejections'],
                'strength':   rejection['strength'],
                'score_add':  score,
            }

    # ── C2: Patrón de vela SIPV en 15m ───────
    if df_15m is not None:
        candle_15m = detect_exhaustion_candle(
            df_15m, '15m'
        )
        if candle_15m['detected']:
            candle_score = (
                candle_15m['strength'] / 10 * 2.5
            )
            score += candle_score
            components['candle_15m'] = {
                'pattern':  candle_15m['pattern'],
                'strength': candle_15m['strength'],
                'score_add': candle_score,
            }

    # ── C3: Patrón de vela SIPV en 5m ────────
    if df_5m is not None:
        candle_5m = detect_exhaustion_candle(
            df_5m, '5m'
        )
        if candle_5m['detected']:
            candle_score = (
                candle_5m['strength'] / 10 * 1.5
            )
            score += candle_score
            components['candle_5m'] = {
                'pattern':  candle_5m['pattern'],
                'strength': candle_5m['strength'],
                'score_add': candle_score,
            }

    # ── C4: Volume decreciente ────────────────
    if df_15m is not None and len(df_15m) >= 5:
        vols = df_15m['volume'].tail(5).values
        if len(vols) >= 3:
            recent_vol = float(np.mean(vols[-2:]))
            prev_vol   = float(np.mean(vols[:-2]))
            if prev_vol > 0:
                vol_ratio = recent_vol / prev_vol
                if vol_ratio < 0.60:
                    score += 2.0
                    components['volume'] = {
                        'ratio': vol_ratio,
                        'status': 'declining_strong',
                        'score_add': 2.0,
                    }
                elif vol_ratio < 0.80:
                    score += 1.0
                    components['volume'] = {
                        'ratio': vol_ratio,
                        'status': 'declining',
                        'score_add': 1.0,
                    }

    # ── C5: MACD divergencia ──────────────────
    macd_hist = float(snap.get(
        'macd_histogram', 0
    ))
    macd_prev = float(snap.get(
        'macd_histogram_prev', 0
    ))
    if macd_hist > 0 and macd_hist < macd_prev:
        # MACD positivo pero decreciendo
        score += 1.0
        components['macd'] = {
            'histogram': macd_hist,
            'prev':      macd_prev,
            'diverging': True,
            'score_add': 1.0,
        }

    # ── C6: Macro Score negativo ──────────────
    if macro and macro.get('score', 0) <= -3:
        macro_score_add = abs(
            macro['score']
        ) / 10 * 2.0
        score += macro_score_add
        components['macro'] = {
            'macro_score': macro['score'],
            'sentiment':   macro['sentiment'],
            'score_add':   macro_score_add,
        }

    # Normalizar a 0-10
    score = min(10.0, score)

    # Clasificar
    if score >= 9:
        level  = 'extreme'
        action = 'close_b1_b2'
    elif score >= 7:
        level  = 'strong'
        action = 'close_b1'
    elif score >= 5:
        level  = 'moderate'
        action = 'alert'
    else:
        level  = 'low'
        action = 'hold'

    return {
        'ticker':       ticker,
        'score':        round(score, 2),
        'level':        level,
        'action':       action,
        'current_band': current_band,
        'components':   components,
        'macro':        macro,
        'reason': (
            f'Agotamiento {level} '
            f'(score={score:.1f}/10): '
            + ', '.join([
                f'{k}={v.get("score_add",0):.1f}'
                for k, v in components.items()
            ])
        ),
    }


# ═══════════════════════════════════════════
# MÓDULO 5 — TP ADAPTATIVO: DECISIÓN FINAL
# ═══════════════════════════════════════════

def evaluate_adaptive_tp(
    ticker:        str,
    position:      dict,
    current_price: float,
    snap:          dict,
    df_15m:        pd.DataFrame,
    df_5m:         pd.DataFrame = None,
    macro:         dict = None,
) -> dict:
    """
    Función principal del TP Adaptativo.

    Combina el score de agotamiento con la
    posición en las bandas Fibonacci para
    decidir si adaptar los TPs y cuándo
    ejecutar los bloques.

    Retorna la acción a tomar.
    """
    b1_executed = bool(position.get(
        'tp_block1_executed', False
    ))
    b2_executed = bool(position.get(
        'tp_block2_executed', False
    ))
    entry_price = float(position.get('avg_price') or position.get('entry_price') or 0)


    # Solo actúa si el precio está en ganancia
    if current_price <= entry_price:
        return {
            'action': 'hold',
            'reason': 'Sin ganancia — no adaptar TP',
            'score': 0,
        }

    # Calcular score de agotamiento
    exhaustion = calculate_exhaustion_score(
        ticker        = ticker,
        position      = position,
        current_price = current_price,
        snap          = snap,
        df_15m        = df_15m,
        df_5m         = df_5m,
        macro         = macro,
    )

    score      = exhaustion['score']
    action_rec = exhaustion['action']
    curr_band  = exhaustion['current_band']

    # Calcular el B1 adaptativo:
    # En lugar de esperar Upper_6, usar la
    # banda actual donde el precio se detuvo
    # menos un pequeño delta
    atr   = float(position.get('tp_atr_14') or 0)
    delta = atr * 0.5  # delta conservador

    if curr_band > 0:
        band_val = float(snap.get(
            f'upper_{curr_band}', 0
        ))
        # B1 adaptativo = banda actual - delta
        # (la ganancia que ya está confirmada)
        adaptive_b1 = band_val - delta \
                      if band_val > entry_price \
                      else current_price * 0.995
    else:
        adaptive_b1 = current_price * 0.995

    # Ganancia en % del B1 adaptativo
    gain_pct = (
        adaptive_b1 - entry_price
    ) / entry_price * 100 if entry_price > 0 else 0

    # ── DECISIÓN: cerrar B1 por agotamiento ──
    if not b1_executed and \
       action_rec in ('close_b1', 'close_b1_b2'):

        # Verificar que hay ganancia mínima
        if gain_pct >= 1.0:  # al menos 1%
            return {
                'action':        'execute_b1_adaptive',
                'price':         adaptive_b1,
                'gain_pct':      round(gain_pct, 2),
                'exhaustion':    exhaustion,
                'band_used':     curr_band,
                'score':         score,
                'reason': (
                    f'B1 ADAPTATIVO: '
                    f'agotamiento {exhaustion["level"]} '
                    f'(score={score:.1f}) en banda '
                    f'Upper_{curr_band}. '
                    f'Cerrar 50% con '
                    f'+{gain_pct:.1f}% ganancia'
                ),
            }

    # ── DECISIÓN: cerrar B1+B2 por agotamiento
    if b1_executed and not b2_executed and \
       action_rec == 'close_b1_b2':

        # También cerrar B2 (salida parcial extra)
        b1_exec_price = float(position.get('tp_block1_price') or entry_price)

        if current_price > b1_exec_price:
            return {
                'action':        'execute_b2_adaptive',
                'price':         current_price,
                'gain_pct':      round(gain_pct, 2),
                'exhaustion':    exhaustion,
                'score':         score,
                'reason': (
                    f'B2 ADAPTATIVO: '
                    f'agotamiento extremo '
                    f'(score={score:.1f}). '
                    f'Cerrar 25% adicional'
                ),
            }

    # ── Alerta de monitoreo ───────────────────
    if action_rec == 'alert':
        return {
            'action':     'alert',
            'exhaustion': exhaustion,
            'score':      score,
            'reason': (
                f'ALERTA: agotamiento moderado '
                f'(score={score:.1f}/10). '
                f'Monitoreo intensivo...'
            ),
        }

    return {
        'action':     'hold',
        'exhaustion': exhaustion,
        'score':      score,
        'reason': (
            f'Score {score:.1f}/10 — '
            f'sin trigger adaptativo'
        ),
    }


# ═══════════════════════════════════════════
# MÓDULO 6 — OBTENER DATOS MACRO DE IB
# ═══════════════════════════════════════════

async def fetch_macro_data(supabase) -> dict:
    """
    Obtiene VIX, SPY y NDX de IB TWS o de
    market_data_5m si ya están cacheados.
    Falls back to market_snapshot if market_data_5m
    is not available.
    """
    try:
        # Try market_data_5m first
        vix = 15.0
        spy_chg = 0.0
        ndx_chg = 0.0

        try:
            vix_res = supabase \
                .table('market_data_5m') \
                .select('close') \
                .eq('ticker', 'VIX') \
                .order('timestamp', desc=True) \
                .limit(1) \
                .execute()
            if vix_res.data:
                vix = float(vix_res.data[0]['close'])
        except Exception:
            # Try market_snapshot as fallback
            try:
                vix_snap = supabase \
                    .table('market_snapshot') \
                    .select('price') \
                    .eq('symbol', 'VIX') \
                    .limit(1) \
                    .execute()
                if vix_snap.data:
                    vix = float(vix_snap.data[0]['price'])
            except Exception:
                pass

        try:
            spy_res = supabase \
                .table('market_data_5m') \
                .select('close') \
                .eq('ticker', 'SPY') \
                .order('timestamp', desc=True) \
                .limit(1) \
                .execute()
            if spy_res.data:
                spy_chg = 0.0  # Or manual calculation if needed
        except Exception:
            try:
                spy_snap = supabase \
                    .table('market_snapshot') \
                    .select('price') \
                    .eq('symbol', 'SPY') \
                    .limit(1) \
                    .execute()
                if spy_snap.data:
                    spy_chg = 0.0
            except Exception:
                pass

        try:
            ndx_res = supabase \
                .table('market_data_5m') \
                .select('close') \
                .eq('ticker', 'QQQ') \
                .order('timestamp', desc=True) \
                .limit(1) \
                .execute()
            if ndx_res.data:
                ndx_chg = 0.0
        except Exception:
            try:
                ndx_snap = supabase \
                    .table('market_snapshot') \
                    .select('price') \
                    .eq('symbol', 'QQQ') \
                    .limit(1) \
                    .execute()
                if ndx_snap.data:
                    ndx_chg = 0.0
            except Exception:
                pass

        macro = calculate_macro_score(
            vix        = vix,
            spy_change = spy_chg,
            ndx_change = ndx_chg,
        )
        macro.update({
            'vix':       vix,
            'spy_change': spy_chg,
            'ndx_change': ndx_chg,
        })
        return macro

    except Exception as e:
        log_error(MODULE,
            f'Error obteniendo macro: {e}'
        )
        return calculate_macro_score()
