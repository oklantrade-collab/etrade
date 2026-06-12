"""
APEX Score v1.0
Adaptive Probability EXpectation

Motor de probabilidad de éxito para Stocks.
Calcula la probabilidad de subida en 4H y 1D.

NO predice el precio exacto.
Calcula la probabilidad y el rango esperado.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from app.core.logger import log_info


# ── Pesos de cada bloque ──────────────────────
APEX_WEIGHTS = {
    'b1_momentum':    0.30,
    'b2_technical':   0.25,
    'b3_fundamental': 0.20,
    'b4_regime':      0.15,
    'b5_sentiment':   0.10,
}

# ── Ajuste de pesos por horizonte ─────────────
APEX_WEIGHTS_4H = {
    'b1_momentum':    0.40,  # flujo domina en 4H
    'b2_technical':   0.30,
    'b3_fundamental': 0.10,  # menos relevante en 4H
    'b4_regime':      0.15,
    'b5_sentiment':   0.05,
}

APEX_WEIGHTS_1D = {
    'b1_momentum':    0.25,
    'b2_technical':   0.25,
    'b3_fundamental': 0.25,  # más relevante en 1D
    'b4_regime':      0.15,
    'b5_sentiment':   0.10,
}


# ════════════════════════════════════════════
# BLOQUE 1 — MOMENTUM DEL FLUJO (30%)
# ════════════════════════════════════════════

def calculate_b1_momentum(
    snap:    dict,
    df_5m:   pd.DataFrame = None,
    df_15m:  pd.DataFrame = None,
    snap_5m: dict = None,
) -> dict:
    """
    Mide la fuerza del flujo comprador.
    Variables: RVOL, Aceleración del precio, Distancia al VWAP, Consistencia del volumen.
    """
    score      = 0.0
    components = {}

    # ── RVOL ──────────────────────────────────
    rvol = float(snap.get('rvol') or 1.0)
    if rvol >= 3.0:
        rvol_score = 100
    elif rvol >= 2.0:
        rvol_score = 85
    elif rvol >= 1.5:
        rvol_score = 70
    elif rvol >= 1.2:
        rvol_score = 50
    elif rvol >= 1.0:
        rvol_score = 30
    else:
        rvol_score = 5

    components['rvol'] = {
        'value': rvol, 'score': rvol_score, 'weight': 0.35,
    }

    # ── Aceleración del precio en 5m ──────────
    price_accel = 0
    if df_5m is not None and len(df_5m) >= 6:
        closes = df_5m['close'].tail(6).values
        recent_move = (float(closes[-1]) - float(closes[-3])) / float(closes[-3]) * 100
        momentum = (float(closes[-1]) - float(closes[0])) / float(closes[0]) * 100

        if recent_move > 1.0:
            price_accel = 90
        elif recent_move > 0.5:
            price_accel = 75
        elif recent_move > 0.2:
            price_accel = 60
        elif recent_move > 0:
            price_accel = 50
        elif recent_move > -0.2:
            price_accel = 40
        else:
            price_accel = 20

        components['price_acceleration'] = {
            'recent_move_pct': round(recent_move, 3),
            'momentum_6c_pct': round(momentum, 3),
            'score': price_accel, 'weight': 0.25,
        }

    # ── Distancia al VWAP ─────────────────────
    price = float(snap.get('price') or 0)
    vwap  = float(snap.get('vwap') or price)
    vwap_score = 50
    if vwap > 0 and price > 0:
        dist_vwap = (price - vwap) / vwap * 100
        if dist_vwap > 2.0:
            vwap_score = 85
        elif dist_vwap > 0.5:
            vwap_score = 70
        elif dist_vwap > 0:
            vwap_score = 55
        elif dist_vwap > -0.5:
            vwap_score = 45
        elif dist_vwap > -2.0:
            vwap_score = 30
        else:
            vwap_score = 15

        components['vwap'] = {
            'dist_pct': round(dist_vwap, 3),
            'score': vwap_score, 'weight': 0.20,
        }

    # ── Consistencia del volumen ───────────────
    vol_consistency = 50
    if df_15m is not None and len(df_15m) >= 10:
        vols = df_15m['volume'].tail(10).values
        vol_trend = np.polyfit(range(len(vols)), vols.astype(float), 1)[0]
        if vol_trend > 0:
            vol_consistency = 70
        else:
            vol_consistency = 35
        components['vol_consistency'] = {
            'trend': 'up' if vol_trend > 0 else 'down',
            'score': vol_consistency, 'weight': 0.20,
        }

    # ── EMA3 / EMA9 FRESH CROSS BONUS ─────────
    ema3 = float(snap.get('ema_3') or 0)
    ema9 = float(snap.get('ema_9') or 0)
    ema_cross_age = int(snap.get('ema3_cross_ema9_age') if snap.get('ema3_cross_ema9_age') is not None else 999)
    ema_cross_score = 0
    if ema3 > ema9:
        if ema_cross_age <= 1:
            ema_cross_score = 100
        elif ema_cross_age <= 3:
            ema_cross_score = 70
        else:
            ema_cross_score = 40
    else:
        ema_cross_score = 10
        
    components['ema_cross_momentum'] = {
        'age': ema_cross_age,
        'score': ema_cross_score, 'weight': 0.25,
    }

    # ── EARLY MOMENTUM 5m BONUS ──────────────────
    # Si en el gráfico de 5 minutos: EMA3 > EMA9 > EMA20 Y las bandas BB están
    # abriéndose, esto indica el INICIO de un movimiento explosivo.
    # Premiamos fuertemente para que APEX seleccione estas acciones.
    early_momentum_5m = 0
    if snap_5m:
        ema3_5m  = float(snap_5m.get('ema_3') or 0)
        ema9_5m  = float(snap_5m.get('ema_9') or 0)
        ema20_5m = float(snap_5m.get('ema_20') or 0)
        bb_exp_5m = bool(snap_5m.get('bb_expanding', False))
        rsi_5m    = float(snap_5m.get('rsi_14') or 50)

        # Perfect alignment: EMA3 > EMA9 > EMA20 on 5m
        if ema3_5m > 0 and ema9_5m > 0 and ema20_5m > 0:
            if ema3_5m > ema9_5m > ema20_5m:
                if bb_exp_5m and rsi_5m < 70:
                    # ¡Setup perfecto! Momentum naciente con bandas abriéndose
                    early_momentum_5m = 100
                elif bb_exp_5m:
                    early_momentum_5m = 80
                elif rsi_5m < 60:
                    early_momentum_5m = 65
                else:
                    early_momentum_5m = 50
            elif ema3_5m > ema9_5m:
                # Parcial alignment
                early_momentum_5m = 35
            else:
                early_momentum_5m = 10
        
        components['early_momentum_5m'] = {
            'ema3_5m': round(ema3_5m, 4) if ema3_5m else 0,
            'ema9_5m': round(ema9_5m, 4) if ema9_5m else 0,
            'ema20_5m': round(ema20_5m, 4) if ema20_5m else 0,
            'bb_expanding_5m': bb_exp_5m,
            'rsi_5m': round(rsi_5m, 1),
            'score': early_momentum_5m, 'weight': 0.20,
        }

    # ── Score final B1 ────────────────────────
    has_early_5m = 'early_momentum_5m' in components
    
    # ── OVERRIDE PARA BREAKOUTS TEMPRANOS ──
    # Si tenemos una explosión inminente en 5m, ignoramos los indicadores rezagados
    # (vol_consistency de 150 mins y price_accel pasados) para que no tiren el puntaje abajo.
    if has_early_5m and early_momentum_5m >= 80:
        weights_used = {
            'rvol': 0.35,        # RVOL toma mucha más importancia
            'price_accel': 0,    # IGNORAR (lagging indicator)
            'vwap': 0.15 if 'vwap' in components else 0,
            'vol_consist': 0,    # IGNORAR (lagging indicator)
            'ema_cross': 0.20 if 'ema_cross_momentum' in components else 0,
            'early_5m': 0.30,    # El setup de 5m toma el control principal
        }
    else:
        weights_used = {
            'rvol': 0.20,
            'price_accel': 0.10 if 'price_acceleration' in components else 0,
            'vwap': 0.10 if 'vwap' in components else 0,
            'vol_consist': 0.15 if 'vol_consistency' in components else 0,
            'ema_cross': 0.25 if 'ema_cross_momentum' in components else 0,
            'early_5m': 0.20 if has_early_5m else 0,
        }
        
    total_w = sum(weights_used.values())

    score = (
        rvol_score * weights_used['rvol'] +
        price_accel * weights_used['price_accel'] +
        vwap_score * weights_used['vwap'] +
        vol_consistency * weights_used['vol_consist'] +
        ema_cross_score * weights_used['ema_cross'] +
        early_momentum_5m * weights_used['early_5m']
    ) / (total_w if total_w > 0 else 1)
    
    # ── Penalización por Sobreextensión (Evitar techos) ────────
    if price > 0:
        ema20 = float(snap.get('ema20') or snap.get('ema_20') or 0)
        if ema20 > 0:
            dist_ema20 = (price - ema20) / ema20 * 100
            if dist_ema20 > 10.0: # Precio está más de 10% arriba de la EMA20 (muy extendido)
                score *= 0.60
                components['overextension_penalty'] = {
                     'dist_ema20': round(dist_ema20, 2),
                     'multiplier': 0.60
                }
            elif dist_ema20 > 5.0:
                score *= 0.85
                components['overextension_penalty'] = {
                     'dist_ema20': round(dist_ema20, 2),
                     'multiplier': 0.85
                }

    return {
        'score': round(score, 2),
        'components': components,
        'rvol': rvol,
        'reason': f'Momentum: RVOL={rvol:.1f}x score={score:.1f}/100',
    }


# ════════════════════════════════════════════
# BLOQUE 2 — CONTEXTO TÉCNICO (25%)
# ════════════════════════════════════════════

def calculate_b2_technical(
    snap:   dict,
    df_15m: pd.DataFrame = None,
    df_4h:  pd.DataFrame = None,
    snap_5m: dict = None,
) -> dict:
    """
    Evalúa el contexto técnico actual.
    Variables: RSI, MACD, Posición vs EMAs, Banda Fibonacci, SAR.
    """
    score      = 0.0
    components = {}
    price = float(snap.get('price') or 0)
    ema20 = float(snap.get('ema20') or snap.get('ema_20') or 0)

    # ── RSI ───────────────────────────────────
    rsi = float(snap.get('rsi_14') or 50)
    if 45 <= rsi <= 65:
        rsi_score = 60
    elif rsi < 30:
        # Solo premiar si el precio NO está en caída libre
        rsi_score = 20 if price < ema20 else 80
    elif 30 <= rsi < 45:
        rsi_score = 70 if price > ema20 else 40
    elif 65 < rsi <= 75:
        rsi_score = 45
    else:
        rsi_score = 15

    components['rsi'] = {'value': rsi, 'score': rsi_score, 'weight': 0.20}

    # ── MACD ──────────────────────────────────
    macd_hist = float(snap.get('macd_histogram') or 0)
    macd_prev = float(snap.get('macd_histogram_prev') or 0)
    if macd_hist > 0 and macd_hist > macd_prev:
        macd_score = 80
    elif macd_hist > 0 and macd_hist <= macd_prev:
        macd_score = 60
    elif macd_hist < 0 and macd_hist > macd_prev:
        macd_score = 45
    else:
        macd_score = 25

    components['macd'] = {
        'histogram': round(macd_hist, 4),
        'growing': macd_hist > macd_prev,
        'score': macd_score, 'weight': 0.20,
    }

    # ── Posición vs EMA ───────────────────────
    ema50 = float(snap.get('ema50') or snap.get('ema_50') or 0)
    ema_score = 50

    if price > 0 and ema20 > 0 and ema50 > 0:
        above_20 = price > ema20
        above_50 = price > ema50
        ema20_above_50 = ema20 > ema50

        if above_20 and above_50 and ema20_above_50:
            ema_score = 90
        elif above_20 and above_50:
            ema_score = 75
        elif above_20 and not above_50:
            ema_score = 40
        elif not above_20 and above_50:
            ema_score = 30
        else:
            # TENDENCIA BAJISTA TOTAL (CASO ABR)
            ema_score = 5

    components['ema_position'] = {
        'price': price, 'ema20': ema20, 'ema50': ema50,
        'score': ema_score, 'weight': 0.20,
    }

    # ── Banda Fibonacci ───────────────────────
    fib_zone_val = snap.get('fibonacci_zone') if snap.get('fibonacci_zone') is not None else snap.get('fib_zone_15m')
    fib_zone = int(fib_zone_val if fib_zone_val is not None else 0)
    fib_score_map = {
        -6: 95, -5: 88, -4: 80, -3: 72, -2: 62, -1: 55,
        0: 50,
        1: 48, 2: 42, 3: 35, 4: 28, 5: 20, 6: 15,
    }
    fib_score = fib_score_map.get(max(-6, min(6, fib_zone)), 50)
    components['fibonacci'] = {'zone': fib_zone, 'score': fib_score, 'weight': 0.20}

    # ── SAR ───────────────────────────────────
    sar_15m = int(snap.get('sar_trend_15m') if snap.get('sar_trend_15m') is not None else 0)
    sar_4h  = int(snap.get('sar_trend_4h') if snap.get('sar_trend_4h') is not None else 0)

    if sar_15m > 0 and sar_4h > 0:
        sar_score = 80
    elif sar_15m > 0:
        sar_score = 60
    elif sar_4h > 0:
        sar_score = 55
    elif sar_15m < 0 and sar_4h < 0:
        sar_score = 20
    else:
        sar_score = 40

    components['sar'] = {
        'sar_15m': sar_15m, 'sar_4h': sar_4h,
        'score': sar_score, 'weight': 0.20,
    }

    # ── Bollinger Bands Expansion ────────────────
    bb_expanding = bool(snap.get('bb_expanding', False))
    bb_expanding_5m = bool(snap_5m.get('bb_expanding', False)) if snap_5m else False
    # Si la expansión está naciendo en 5m, máxima puntuación
    if bb_expanding_5m and bb_expanding:
        bb_score = 100  # Ambas temporalidades expandiéndose
    elif bb_expanding_5m:
        bb_score = 95   # Naciendo en 5m (setup temprano ideal)
    elif bb_expanding:
        bb_score = 80   # Solo en 15m
    else:
        bb_score = 45
    components['bb_expansion'] = {
        'expanding_15m': bb_expanding,
        'expanding_5m': bb_expanding_5m,
        'score': bb_score, 'weight': 0.15,
    }

    # ── Score final B2 ────────────────────────
    score = (
        rsi_score * 0.15 + macd_score * 0.15 +
        ema_score * 0.20 + fib_score * 0.20 + sar_score * 0.15 + bb_score * 0.15
    )

    return {
        'score': round(score, 2),
        'components': components,
        'rsi': rsi, 'fib_zone': fib_zone,
        'reason': f'Técnico: RSI={rsi:.0f} Fib=z{fib_zone} score={score:.1f}/100',
    }


# ════════════════════════════════════════════
# BLOQUE 3 — VALORACIÓN FUNDAMENTAL (20%)
# ════════════════════════════════════════════

def calculate_b3_fundamental(fundamental_cache: dict) -> dict:
    """
    Usa el valuation_engine.py que ya tenemos.
    Variables: Piotroski, Margen de seguridad, Altman Z-Score, Pro Score.
    """
    score      = 0.0
    components = {}

    # ── Piotroski F-Score ─────────────────────
    piotroski = int(fundamental_cache.get('piotroski_score', 4))
    piotroski_score = piotroski / 9 * 100
    components['piotroski'] = {
        'score_raw': piotroski, 'score': round(piotroski_score, 1), 'weight': 0.30,
    }

    # ── Margen de seguridad ───────────────────
    margin = float(fundamental_cache.get('margin_of_safety', 0))
    if margin >= 20:
        margin_score = 90
    elif margin >= 10:
        margin_score = 75
    elif margin >= 0:
        margin_score = 60
    elif margin >= -10:
        margin_score = 45
    elif margin >= -20:
        margin_score = 30
    else:
        margin_score = 15
    components['margin_of_safety'] = {
        'value': margin, 'score': margin_score, 'weight': 0.30,
    }

    # ── Altman Z-Score ────────────────────────
    altman_zone = str(fundamental_cache.get('altman_zone', 'grey'))
    altman_score = {'safe': 80, 'grey': 50, 'danger': 20}.get(altman_zone, 50)
    components['altman'] = {
        'zone': altman_zone, 'score': altman_score, 'weight': 0.20,
    }

    # ── Pro Score existente ───────────────────
    pro_score = float(fundamental_cache.get('fundamental_score', 50))
    components['pro_score'] = {
        'value': pro_score, 'score': pro_score, 'weight': 0.20,
    }

    # ── Score final B3 ────────────────────────
    score = (
        piotroski_score * 0.30 + margin_score * 0.30 +
        altman_score * 0.20 + pro_score * 0.20
    )

    return {
        'score': round(score, 2),
        'components': components,
        'piotroski': piotroski, 'margin': margin,
        'reason': f'Fundamental: Piotroski={piotroski}/9 Margen={margin:.1f}% score={score:.1f}/100',
    }


# ════════════════════════════════════════════
# BLOQUE 4 — RÉGIMEN DEL MERCADO (15%)
# ════════════════════════════════════════════

def calculate_b4_regime(
    macro: dict, snap: dict, df_daily: pd.DataFrame = None,
) -> dict:
    """
    Detecta el régimen actual del mercado.
    Tipos: trending_up, trending_down, mean_reversion, high_volatility, low_volatility.
    """
    score      = 0.0
    components = {}

    adx = float(snap.get('adx') or 25)
    atr = float(snap.get('atr') or 0)
    price = float(snap.get('price') or 1)
    atr_pct = (atr / price * 100) if price > 0 else 0

    sar_4h_val = snap.get('sar_trend_4h') if snap.get('sar_trend_4h') is not None else 0
    if adx > 35 and sar_4h_val > 0:
        regime_type, regime_score = 'trending_up', 80
    elif adx > 35 and sar_4h_val < 0:
        regime_type, regime_score = 'trending_down', 25
    elif adx < 20 and atr_pct < 1.5:
        regime_type, regime_score = 'low_volatility', 55
    elif atr_pct > 3.0:
        regime_type, regime_score = 'high_volatility', 45
    else:
        regime_type, regime_score = 'mean_reversion', 60

    components['regime'] = {
        'type': regime_type, 'adx': adx,
        'atr_pct': round(atr_pct, 2),
        'score': regime_score, 'weight': 0.40,
    }

    # ── Macro (VIX/SPY/NDX) ───────────────────
    macro_score_raw = float(macro.get('score') or 0)
    macro_score = (macro_score_raw + 10) / 20 * 100
    components['macro'] = {
        'score_raw': macro_score_raw,
        'score': round(macro_score, 1),
        'sentiment': macro.get('sentiment', ''),
        'weight': 0.40, 'flags': macro.get('flags', []),
    }

    # ── Sector performance (MTF proxy) ────────
    mtf = float(snap.get('mtf_score') or 0)
    sector_score = (mtf + 1) / 2 * 100
    components['sector'] = {
        'mtf': mtf, 'score': round(sector_score, 1), 'weight': 0.15,
    }

    # ── Estructura Diaria (Higher Lows) ───────
    daily_structure_score = 50
    if df_daily is not None and len(df_daily) >= 2:
        try:
            curr_low = float(df_daily.iloc[-1].get('low', df_daily.iloc[-1].get('Low', 0)))
            prev_low = float(df_daily.iloc[-2].get('low', df_daily.iloc[-2].get('Low', 0)))
            if curr_low > 0 and prev_low > 0:
                if curr_low > prev_low:
                    daily_structure_score = 80  # Higher low (fuerza alcista)
                elif curr_low < prev_low:
                    daily_structure_score = 45  # Lower low (debilidad leve)
        except Exception:
            pass
            
    components['daily_structure'] = {
        'score': daily_structure_score, 'weight': 0.15,
    }

    score = regime_score * 0.35 + macro_score * 0.35 + sector_score * 0.15 + daily_structure_score * 0.15

    return {
        'score': round(score, 2),
        'regime_type': regime_type,
        'components': components, 'adx': adx,
        'reason': f'Régimen: {regime_type} ADX={adx:.0f} Macro={macro_score_raw:.1f} score={score:.1f}/100',
    }


# ════════════════════════════════════════════
# BLOQUE 5 — SENTIMIENTO (10%)
# ════════════════════════════════════════════

def calculate_b5_sentiment(fundamental_cache: dict, snap: dict, ia_score: float = None) -> dict:
    """
    Sentimiento específico para stocks.
    Variables: Analyst rating, Short interest, Earnings proximity, Valuation status, AI Score.
    """
    score      = 0.0
    components = {}

    # ── Analyst Rating (30%) ──────────────────
    analyst_rating = float(fundamental_cache.get('analyst_rating', 5) or 5)
    analyst_score = analyst_rating * 10
    components['analyst'] = {
        'rating': analyst_rating, 'score': analyst_score, 'weight': 0.30,
    }

    # ── AI Score (Gemini/Qwen) (30%) ───────────
    if ia_score is not None:
        # ia_score is usually 0-10
        final_ia_score = ia_score * 10
        components['ai_sentiment'] = {
            'value': ia_score, 'score': final_ia_score, 'weight': 0.30,
        }
    else:
        final_ia_score = 50 # Fallback neutral
        components['ai_sentiment'] = {
            'value': 5.0, 'score': 50, 'weight': 0.30, 'fallback': True
        }

    # ── Short Interest (10%) ──────────────────
    short_pct = float(fundamental_cache.get('short_interest_pct', 5) or 5)
    if short_pct < 5:
        short_score = 70
    elif short_pct < 10:
        short_score = 55
    elif short_pct < 20:
        short_score = 45
    else:
        short_score = 30
    components['short_interest'] = {
        'pct': short_pct, 'score': short_score, 'weight': 0.10,
    }

    # ── Earnings Proximity (20%) ──────────────
    days_to_earnings = int(fundamental_cache.get('days_to_earnings', 30) or 30)
    if days_to_earnings < 3:
        earnings_score = 25
    elif days_to_earnings < 7:
        earnings_score = 40
    elif days_to_earnings < 14:
        earnings_score = 55
    elif days_to_earnings < 30:
        earnings_score = 65
    else:
        earnings_score = 75
    components['earnings'] = {
        'days_to': days_to_earnings, 'score': earnings_score, 'weight': 0.20,
    }

    # ── Valuation Status (10%) ────────────────
    val_status = str(fundamental_cache.get('valuation_status', 'fairly_valued'))
    val_score = {
        'undervalued': 85, 'fairly_valued': 60,
        'overvalued': 30, 'unknown': 50,
    }.get(val_status, 50)
    components['valuation'] = {
        'status': val_status, 'score': val_score, 'weight': 0.10,
    }

    score = (
        analyst_score * 0.30 + final_ia_score * 0.30 +
        short_score * 0.10 + earnings_score * 0.20 + val_score * 0.10
    )

    return {
        'score': round(score, 2),
        'components': components,
        'reason': f'Sentimiento: Analyst={analyst_rating:.1f} AI={ia_score if ia_score else 5.0} DaysEarn={days_to_earnings} score={score:.1f}/100',
    }


# ════════════════════════════════════════════
# FUNCIÓN PRINCIPAL — APEX SCORE
# ════════════════════════════════════════════

def calculate_apex_score(
    ticker:            str,
    snap:              dict,
    fundamental_cache: dict,
    macro:             dict,
    df_5m:             pd.DataFrame = None,
    df_15m:            pd.DataFrame = None,
    df_4h:             pd.DataFrame = None,
    df_daily:          pd.DataFrame = None,
    ia_score:          float = None,
) -> dict:
    """
    Función principal del APEX Score.
    Combina los 5 bloques con pesos diferenciados para 4H y 1D.
    Retorna la probabilidad de subida y el retorno esperado con 3 escenarios.
    """
    price = float(snap.get('price') or 0)
    atr   = float(snap.get('atr') or (price * 0.02))

    # ── Construir snap_5m para indicadores de 5 minutos ──
    snap_5m = None
    if df_5m is not None and len(df_5m) >= 20:
        try:
            close_5m = pd.to_numeric(df_5m['close' if 'close' in df_5m.columns else 'Close'], errors='coerce').dropna()
            ema3_5m_val = float(close_5m.ewm(span=3, adjust=False).mean().iloc[-1])
            ema9_5m_val = float(close_5m.ewm(span=9, adjust=False).mean().iloc[-1])
            ema20_5m_val = float(close_5m.ewm(span=20, adjust=False).mean().iloc[-1])
            rsi_col = 'rsi_14' if 'rsi_14' in df_5m.columns else None
            rsi_5m_val = float(df_5m[rsi_col].iloc[-1]) if rsi_col else 50.0
            # Detect BB expansion in 5m
            bb_upper_col = 'bb_upper' if 'bb_upper' in df_5m.columns else None
            bb_lower_col = 'bb_lower' if 'bb_lower' in df_5m.columns else None
            bb_exp_5m = False
            if bb_upper_col and bb_lower_col and len(df_5m) >= 3:
                last_row = df_5m.iloc[-1]
                prev_row = df_5m.iloc[-2]
                bb_exp_5m = (
                    float(last_row[bb_upper_col]) > float(prev_row[bb_upper_col]) and
                    float(last_row[bb_lower_col]) < float(prev_row[bb_lower_col])
                )
            snap_5m = {
                'ema_3': ema3_5m_val,
                'ema_9': ema9_5m_val,
                'ema_20': ema20_5m_val,
                'rsi_14': rsi_5m_val,
                'bb_expanding': bb_exp_5m,
            }
        except Exception:
            snap_5m = None

    # ── Calcular los 5 bloques ────────────────
    b1 = calculate_b1_momentum(snap, df_5m, df_15m, snap_5m=snap_5m)
    b2 = calculate_b2_technical(snap, df_15m, df_4h, snap_5m=snap_5m)
    b3 = calculate_b3_fundamental(fundamental_cache)
    b4 = calculate_b4_regime(macro, snap, df_daily)
    b5 = calculate_b5_sentiment(fundamental_cache, snap, ia_score=ia_score)

    blocks = {
        'b1_momentum':    b1['score'],
        'b2_technical':   b2['score'],
        'b3_fundamental': b3['score'],
        'b4_regime':      b4['score'],
        'b5_sentiment':   b5['score'],
    }

    # ── MOMENTUM OVERRIDE ──
    # Si RVOL es alto y Momentum (B1) es muy fuerte, los pesos cambian dinámicamente
    # para no ser castigados severamente por B3 (Fundamental)
    rvol_val = float(snap.get('rvol') or 1.0)
    is_momentum = rvol_val >= 1.5 or b1['score'] >= 75
    
    if is_momentum:
        w_4h = {
            'b1_momentum':    0.45,
            'b2_technical':   0.35,
            'b3_fundamental': 0.05,
            'b4_regime':      0.10,
            'b5_sentiment':   0.05,
        }
        w_1d = {
            'b1_momentum':    0.35,
            'b2_technical':   0.35,
            'b3_fundamental': 0.10,
            'b4_regime':      0.10,
            'b5_sentiment':   0.10,
        }
    else:
        w_4h = APEX_WEIGHTS_4H
        w_1d = APEX_WEIGHTS_1D

    # ── APEX Score 4H (flujo domina) ──────────
    apex_4h = sum(blocks[k] * w_4h[k] for k in blocks)
    # ── APEX Score 1D (fundamental importa) ───
    apex_1d = sum(blocks[k] * w_1d[k] for k in blocks)

    apex_4h = round(max(5, min(95, apex_4h)), 1)
    apex_1d = round(max(5, min(95, apex_1d)), 1)

    # ── Retorno esperado ──────────────────────
    atr_pct = atr / price * 100 if price > 0 else 2
    prob_factor_4h = (apex_4h - 50) / 50
    prob_factor_1d = (apex_1d - 50) / 50
    return_4h = atr_pct * 0.5 * prob_factor_4h
    return_1d = atr_pct * 1.0 * prob_factor_1d

    # ── Confianza ─────────────────────────────
    scores = list(blocks.values())
    divergence = float(np.std(scores))
    if divergence < 10 and apex_4h > 65:
        confidence = 'high'
    elif divergence < 20:
        confidence = 'medium'
    else:
        confidence = 'low'

    # ── Edge estadístico ──────────────────────
    edge_4h = apex_4h - 50
    edge_1d = apex_1d - 50

    # ── 3 Escenarios ──────────────────────────
    scenarios = {
        'bull': {
            'probability': min(95, apex_4h + 15),
            'price_target': round(price * (1 + atr_pct / 100 * 1.5), 4),
            'return_pct': round(atr_pct * 1.5, 2),
            'description': 'Momentum continúa fuerte',
        },
        'base': {
            'probability': apex_4h,
            'price_target': round(price * (1 + return_4h / 100), 4),
            'return_pct': round(return_4h, 2),
            'description': 'Escenario más probable',
        },
        'bear': {
            'probability': max(5, 100 - apex_4h - 10),
            'price_target': round(price * (1 - atr_pct / 100), 4),
            'return_pct': round(-atr_pct, 2),
            'description': 'Retroceso hacia soporte',
        },
    }

    # ── Clasificación del score ────────────────
    if apex_4h >= 75:
        signal, color, emoji = 'STRONG_BUY', '#00C896', '🟢🟢'
    elif apex_4h >= 60:
        signal, color, emoji = 'BUY', '#4FC3F7', '🟢'
    elif apex_4h >= 45:
        signal, color, emoji = 'NEUTRAL', '#FFB74D', '🟡'
    elif apex_4h >= 30:
        signal, color, emoji = 'CAUTION', '#FF8A65', '🟠'
    else:
        signal, color, emoji = 'AVOID', '#FF4757', '🔴'

    log_info('APEX',
        f'{emoji} {ticker}: APEX_4H={apex_4h}% APEX_1D={apex_1d}% '
        f'({signal}) conf={confidence} edge={edge_4h:+.1f}%'
    )

    return {
        'ticker': ticker,
        'price': price,
        'apex_score_4h': apex_4h,
        'apex_score_1d': apex_1d,
        'signal': signal,
        'color': color,
        'confidence': confidence,
        'edge_4h': round(edge_4h, 1),
        'edge_1d': round(edge_1d, 1),
        'return_expected_4h': round(return_4h, 3),
        'return_expected_1d': round(return_1d, 3),
        'scenarios': scenarios,
        'blocks': blocks,
        'regime_type': b4['regime_type'],
        'detail': {
            'b1': b1, 'b2': b2, 'b3': b3, 'b4': b4, 'b5': b5,
        },
        'calculated_at': datetime.now(timezone.utc).isoformat(),
        'valid_until_4h': (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
        'valid_until_1d': (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
    }
