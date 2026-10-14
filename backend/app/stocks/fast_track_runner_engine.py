"""
eTrade v5.0 — FAST-TRACK IPO SUPER-RUNNERS & ALPHA RUNNERS ENGINE
=================================================================
Módulo especializado para la operativa de alta volatilidad en Super-Runners e IPOs
(Caso de éxito arquitectónico: JBDI, PFAI).

Pilares Operativos:
A. ENTRADA AL OPEN (08:30 / 09:30 ET):
   - Muestreo en 1ra o 2da vela de 5m con Gap moderado (+10% a +45%).
   - Si Gap > +50%, filtro Opening Range Breakout (ORB-5m: romper High de vela 1).
   - Volumen inicial masivo (>= 500k o RVOL_5m >= 2.5x) y ADX alcista.
   - Asignación inicial ligera (30% del capital objetivo) para permitir Pyramiding.
   - Stop Loss dinámico inicial a 1.5 * ATR_5m bajo el mínimo de entrada.

B. MATRIZ MULTI-TEMPORAL DE SALIDAS (1H, 15m, 5m):
   1. Temporalidad 1H:
      - Tendencia Viva: EMA3 > EMA9 > EMA20 con pendiente positiva -> HOLD.
      - Monitoreo In-Flight cada 15m: Vela en formación SIPV BUY -> HOLD.
      - Ruptura de Open 1H: Vela en formación SIPV SELL perdiendo Open_1H -> Venta Parcial 30%.
      - Clímax 1H: Vela en formación supera en >= 70% el tamaño de la vela previa (H-L)
        estando fuera de Bandas de Bollinger / UPPER_6 -> Venta Parcial 40%.
      - Cierre en Extremo: Precio alcanza UPPER_6 de 1H o RSI_1H >= 80 -> Venta Parcial 40%.
   2. Temporalidad 15m:
      - Trailing Stop Dinámico por EMA9: Si EMA9_15m[t] > EMA9_15m[t-1], el Stop Loss sube a
        (EMA9_15m - Delta), con Delta dinámico proporcional a volatilidad.
      - Vela Clímax de 15m: Rango (H-L) es el mayor de las últimas 9 velas, (C-O) > 1.2x anterior,
        Close > BB_Upper_15m y mecha superior (H-C) >= 10% del rango total -> Venta Parcial 40%.
      - Apertura en Expansión: OPEN > BB_Upper_15m y SIPV BUY -> HOLD.
      - UPPER_6 o RSI_15m >= 80 -> Venta Parcial 40%.

C. RECOMPRA INTELIGENTE (SCALING-IN / PYRAMIDING):
   - Condición 1 (Estructura): Low_15m > Low_15m_prev AND Low_1H > Low_1H_prev AND EMA3_15m > EMA9_15m.
     Gatillo en 5m: Low_5m <= (EMA9_5m + Delta).
   - Condición 2 (Boca de Cocodrilo): BB_Upper_15m ascendente y BB_Lower_15m descendente.
     Gatillo en 5m: Low_5m <= (EMA9_5m + Delta).
   - Candado Anti-Distribución: Prohibido recomprar si hubo venta parcial por clímax en 45 mins.
   - Candado Livermore: Solo promediar al alza (Precio Actual > Precio Compra Previo).
   - Blindaje: Stop Loss de la posición global se sube a Break-Even (Riesgo Cero).
   - Límite: Máximo 2 recompras escalonadas (Tranches: 30% + 35% + 35%).
"""

import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple

from app.core.logger import log_info, log_warning, log_error, log_debug
from app.strategy.panic_recovery_gate import calculate_fibonacci_bands

MODULE = "FAST_TRACK_RUNNER"


def _safe_col(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Retorna la serie de la columna de forma case-insensitive."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    if col_name in df.columns:
        return df[col_name].astype(float)
    cap = col_name.capitalize()
    if cap in df.columns:
        return df[cap].astype(float)
    upper = col_name.upper()
    if upper in df.columns:
        return df[upper].astype(float)
    return pd.Series(dtype=float)


def calculate_fast_track_delta(df_15m: Optional[pd.DataFrame], ema9_price: float) -> float:
    """
    Calcula un Delta dinámico y proporcional para el Trailing Stop en 15m.
    Delta = max(0.08, 0.35 * ATR_15m) o el 1.5% de EMA9.
    Garantiza que el colchón se adapta al nivel de precio y volatilidad real del ticker.
    """
    if df_15m is not None and len(df_15m) >= 5:
        try:
            h = _safe_col(df_15m, 'high')
            l = _safe_col(df_15m, 'low')
            c = _safe_col(df_15m, 'close')
            tr = np.maximum(h - l, np.maximum(abs(h - c.shift(1)), abs(l - c.shift(1))))
            atr = float(tr.rolling(14, min_periods=3).mean().iloc[-1])
            if not np.isnan(atr) and atr > 0:
                delta = max(0.08, 0.35 * atr)
                return round(delta, 3)
        except Exception as e:
            log_debug(MODULE, f"Error calculando Delta dinámico ATR: {e}")

    # Fallback proporcional: 1.5% de EMA9 (mínimo 8 centavos)
    return max(0.08, round(ema9_price * 0.015, 3))


# -------------------------------------------------------------------------
# A. EVALUACIÓN DE ENTRADA INICIAL AL OPEN (08:30 / 09:30 ET)
# -------------------------------------------------------------------------
def evaluate_fast_track_entry(
    ticker: str,
    df_5m: Optional[pd.DataFrame],
    df_15m: Optional[pd.DataFrame],
    df_1h: Optional[pd.DataFrame],
    df_1d: Optional[pd.DataFrame],
    gap_pct: float,
    current_time_et: Optional[datetime] = None,
    config: Optional[dict] = None
) -> dict:
    """
    Evalúa la compra al Open para IPO Super-Runners y Alpha Runners:
    - 1ra o 2da vela de 5m de la sesión.
    - Gap Up moderado (+10% a +45%) o confirmación ORB-5m si > +50%.
    - RVOL_5m >= 2.5x o Volumen_5m >= 500,000 acciones.
    - ADX alcista en 1H o 15m.
    - Tranche inicial: 30% del tamaño de posición objetivo.
    """
    res = {
        'is_valid': False,
        'ticker': ticker,
        'entry_price': 0.0,
        'initial_stop_loss': 0.0,
        'position_tranche_pct': 0.30,
        'rule_code': 'NONE',
        'reason': ''
    }

    if df_5m is None or len(df_5m) < 2:
        res['reason'] = "Insuficientes velas de 5m"
        return res

    try:
        c5 = _safe_col(df_5m, 'close')
        o5 = _safe_col(df_5m, 'open')
        h5 = _safe_col(df_5m, 'high')
        l5 = _safe_col(df_5m, 'low')
        v5 = _safe_col(df_5m, 'volume')

        cur_c = float(c5.iloc[-1])
        cur_o = float(o5.iloc[-1])
        cur_h = float(h5.iloc[-1])
        cur_l = float(l5.iloc[-1])
        cur_v = float(v5.iloc[-1])

        # 1. Filtro de Gap de Apertura
        if gap_pct < 10.0:
            res['reason'] = f"Gap {gap_pct:.1f}% insuficiente para Super-Runner (mínimo +10.0%)"
            return res

        # Si el gap es extremo (> +50%), exigir ORB-5m (2da vela rompe High de 1ra vela)
        if gap_pct > 50.0:
            if len(df_5m) >= 2:
                prev_h = float(h5.iloc[-2])
                if cur_c <= prev_h:
                    res['reason'] = f"Gap parabólico ({gap_pct:.1f}% > 50%): Esperando confirmación ORB-5m (Close ${cur_c:.2f} <= High previo ${prev_h:.2f})"
                    return res
            else:
                res['reason'] = f"Gap parabólico ({gap_pct:.1f}% > 50%): No comprar a ciegas en 1ra vela; esperar 2da vela"
                return res

        # 2. Filtro de Volumen y Combustible Inicial
        vol_ma = float(v5.rolling(10, min_periods=2).mean().iloc[-1]) if len(v5) >= 2 else cur_v
        rvol_5m = (cur_v / vol_ma) if vol_ma > 0 else 1.0

        has_massive_vol = (cur_v >= 500_000) or (rvol_5m >= 2.5)
        if not has_massive_vol:
            res['reason'] = f"Volumen 5m insuficiente ({cur_v:,.0f} sh, RVOL={rvol_5m:.1f}x < 2.5x)"
            return res

        # 3. Tendencia 1H / 15m (ADX y EMAs)
        adx_bullish = False
        target_df = df_1h if (df_1h is not None and len(df_1h) >= 28) else df_15m
        if target_df is not None and len(target_df) >= 28:
            try:
                from ta.trend import ADXIndicator
                th = _safe_col(target_df, 'high')
                tl = _safe_col(target_df, 'low')
                tc = _safe_col(target_df, 'close')
                adx_ind = ADXIndicator(th, tl, tc, window=14)
                adx_val = float(adx_ind.adx().iloc[-1])
                di_pos = float(adx_ind.adx_pos().iloc[-1])
                di_neg = float(adx_ind.adx_neg().iloc[-1])
                adx_bullish = (adx_val >= 18.0 and di_pos > di_neg) or (adx_val >= 25.0)
            except Exception as e_adx:
                log_debug(MODULE, f"ADX calculation skipped: {e_adx}")
                adx_bullish = True
        else:
            # En datos jóvenes (IPOs sin historial amplio), el momentum de apertura manda
            adx_bullish = True

        # Si es IPO joven (menos de 15 velas en 1D), el momentum de apertura de 5m manda
        is_young_ipo = (df_1d is not None and len(df_1d) <= 15)
        if not adx_bullish and not is_young_ipo:
            res['reason'] = "Filtro ADX macro sin alineación alcista confirmada"
            return res

        # 4. Stop Loss Inicial Dinámico (1.5 * ATR_5m por debajo del Low de entrada)
        tr5 = np.maximum(h5 - l5, np.maximum(abs(h5 - c5.shift(1)), abs(l5 - c5.shift(1))))
        atr_5m = float(tr5.rolling(14, min_periods=2).mean().iloc[-1])
        if np.isnan(atr_5m) or atr_5m <= 0:
            atr_5m = cur_c * 0.02

        init_sl = round(cur_l - (1.5 * atr_5m), 2)
        if init_sl <= 0 or init_sl >= cur_c:
            init_sl = round(cur_c * 0.95, 2)

        res.update({
            'is_valid': True,
            'entry_price': cur_c,
            'initial_stop_loss': init_sl,
            'position_tranche_pct': 0.30,
            'rule_code': 'FT_RUNNER_BUY',
            'reason': (
                f"Entrada Fast-Track IPO/Alpha al Open: Gap +{gap_pct:.1f}%, Vol 5m {cur_v:,.0f} sh (RVOL {rvol_5m:.1f}x), "
                f"Close=${cur_c:.2f}, Stop Inicial=${init_sl:.2f} (Tranche 30%)."
            )
        })
        return res

    except Exception as e:
        log_error(MODULE, f"Error evaluando Fast-Track Entry para {ticker}: {e}")
        res['reason'] = str(e)
        return res


# -------------------------------------------------------------------------
# B. EVALUACIÓN MULTI-TIMEFRAME DE SALIDAS Y CIERRES PARCIALES (1H & 15m)
# -------------------------------------------------------------------------
def evaluate_fast_track_exits(
    position: dict,
    df_5m: Optional[pd.DataFrame],
    df_15m: Optional[pd.DataFrame],
    df_1h: Optional[pd.DataFrame],
    current_price: float,
    current_time_utc: Optional[datetime] = None
) -> dict:
    """
    Motor Agudo Multi-Timeframe de Cierres Parciales y Trailing Stops para Super-Runners:
    - 1H: Muestreo in-flight cada 15m de vela expansiva (+70% clímax) y ruptura de Open con SIPV SELL.
    - 15m: Trailing Stop dinámico por pendiente ascendente de EMA9 (EMA9 - Delta).
    - 15m: Vela de Clímax con mecha superior >= 10% del rango fuera de BB -> Venta Parcial 40%.
    - Cierre Total: Perforación de Trailing Stop en 15m o Salida EOD a las 15:50 ET.
    """
    res = {
        'should_exit': False,
        'action': 'HOLD',
        'shares_to_sell': 0,
        'pct_to_sell': 0,
        'rule_code': 'NONE',
        'reason': '',
        'should_update_sl': False,
        'new_stop_loss': 0.0,
        'sl_reason': ''
    }

    if not position or current_price <= 0:
        return res

    entry_p = float(position.get('avg_price') or position.get('entry_price') or 0.0)
    current_shares = int(float(position.get('shares_remaining') or position.get('shares') or 0))
    if entry_p <= 0 or current_shares <= 0:
        return res

    gain_pct = (current_price - entry_p) / entry_p * 100.0
    cur_sl = float(position.get('stop_loss') or 0.0)
    partial_1_done = bool(position.get('ft_partial_1_done') or position.get('tp_block1_executed'))
    partial_2_done = bool(position.get('ft_partial_2_done'))

    # ---------------------------------------------------------------------
    # 1. EVALUACIÓN 15 MINUTOS: TRAILING STOP DINÁMICO POR PENDIENTE DE EMA9
    # ---------------------------------------------------------------------
    if df_15m is not None and len(df_15m) >= 5:
        try:
            c15 = _safe_col(df_15m, 'close')
            o15 = _safe_col(df_15m, 'open')
            h15 = _safe_col(df_15m, 'high')
            l15 = _safe_col(df_15m, 'low')

            ema9_15 = c15.ewm(span=9, adjust=False).mean()
            ema9_now = float(ema9_15.iloc[-1])
            ema9_prev = float(ema9_15.iloc[-2])

            delta_15m = calculate_fast_track_delta(df_15m, ema9_now)

            # Si EMA9 en 15m es ascendente (EMA9_now > EMA9_prev), subir el Trailing Stop a (EMA9 - Delta)
            if ema9_now > ema9_prev:
                proposed_tsl = round(ema9_now - delta_15m, 2)
                # Solo subir el Stop Loss, nunca bajarlo, y mantenerlo por debajo del precio actual
                if proposed_tsl > cur_sl and proposed_tsl < current_price:
                    res['should_update_sl'] = True
                    res['new_stop_loss'] = proposed_tsl
                    res['sl_reason'] = f"Trailing Stop 15m EMA9 Ascendente: ${proposed_tsl:.2f} (EMA9 ${ema9_now:.2f} - Delta ${delta_15m:.2f})"
                    cur_sl = proposed_tsl

            # Comprobar si el precio perforó el Trailing Stop
            if cur_sl > 0 and current_price <= cur_sl:
                res.update({
                    'should_exit': True,
                    'action': 'FULL_EXIT',
                    'shares_to_sell': current_shares,
                    'pct_to_sell': 100,
                    'rule_code': 'FT_TRAILING_STOP_HIT',
                    'reason': f"Trailing Stop 15m ejecutado: Precio (${current_price:.2f}) <= SL (${cur_sl:.2f}). Asegurando beneficio final."
                })
                return res

            # -----------------------------------------------------------------
            # 2. VELA DE CLÍMAX EN 15m: MECHA SUPERIOR >= 10% FUERA DE BOLLINGER
            # -----------------------------------------------------------------
            if not partial_1_done and current_shares >= 2:
                # Bollinger Bands 15m
                sma20_15 = float(c15.rolling(20, min_periods=5).mean().iloc[-1])
                std20_15 = float(c15.rolling(20, min_periods=5).std().fillna(0).iloc[-1])
                bb_up_15 = sma20_15 + 2.0 * std20_15

                cur_h15 = max(float(h15.iloc[-1]), current_price)
                cur_l15 = min(float(l15.iloc[-1]), current_price)
                cur_o15 = float(o15.iloc[-1])
                cur_c15 = current_price
                cur_range15 = max(1e-6, cur_h15 - cur_l15)

                # Comparar tamaño con las 9 velas anteriores de 15m
                prev_9_ranges = (h15.iloc[-10:-1] - l15.iloc[-10:-1]).values if len(h15) >= 10 else []
                is_largest_range_9 = (len(prev_9_ranges) > 0 and cur_range15 > np.max(prev_9_ranges))

                # Expansión del cuerpo: (Close - Open) > 1.20 * (Close_prev - Open_prev)
                prev_body = abs(float(c15.iloc[-2]) - float(o15.iloc[-2])) if len(c15) >= 2 else 0.0
                cur_body = cur_c15 - cur_o15
                body_expanded = (cur_body > 1.20 * prev_body) or (cur_body > 0 and prev_body <= 0)

                # Mecha Superior de Rechazo: (High - Close) >= 10% del rango total de la vela
                upper_wick = cur_h15 - max(cur_o15, cur_c15)
                upper_wick_pct = upper_wick / cur_range15

                # Fuera de Bollinger o rozando la banda
                outside_bb15 = (cur_c15 >= bb_up_15 * 0.995) or (cur_h15 >= bb_up_15)

                if is_largest_range_9 and body_expanded and outside_bb15 and upper_wick_pct >= 0.10:
                    shares_sell = max(1, int(current_shares * 0.40))
                    res.update({
                        'should_exit': True,
                        'action': 'PARTIAL_SELL_40',
                        'shares_to_sell': shares_sell,
                        'pct_to_sell': 40,
                        'rule_code': 'FT_PARTIAL_SELL',
                        'reason': (
                            f"Vela Clímax 15m detectada: Rango ${cur_range15:.2f} > 9 velas previas, "
                            f"Mecha superior {upper_wick_pct*100:.1f}% >= 10%, Close ${cur_c15:.2f} > BB Upper ${bb_up_15:.2f}. "
                            f"Cierre Parcial del 40% ({shares_sell} sh @ ${current_price:.2f}, +{gain_pct:.1f}%)."
                        )
                    })
                    return res

        except Exception as e_15m:
            log_warning(MODULE, f"Error en evaluación de salidas 15m: {e_15m}")

    # ---------------------------------------------------------------------
    # 3. EVALUACIÓN 1 HORA: IN-FLIGHT EXPANSION (+70%) & RUPTURA OPEN 1H
    # ---------------------------------------------------------------------
    if df_1h is not None and len(df_1h) >= 3 and current_shares >= 2:
        try:
            c1h = _safe_col(df_1h, 'close')
            o1h = _safe_col(df_1h, 'open')
            h1h = _safe_col(df_1h, 'high')
            l1h = _safe_col(df_1h, 'low')

            cur_o1h = float(o1h.iloc[-1])
            cur_h1h = max(float(h1h.iloc[-1]), current_price)
            cur_l1h = min(float(l1h.iloc[-1]), current_price)
            cur_range1h = max(1e-6, cur_h1h - cur_l1h)

            prev_h1h = float(h1h.iloc[-2])
            prev_l1h = float(l1h.iloc[-2])
            prev_range1h = max(1e-6, prev_h1h - prev_l1h)

            # Bollinger Bands 1H
            sma20_1h = float(c1h.rolling(20, min_periods=3).mean().iloc[-1])
            std20_1h = float(c1h.rolling(20, min_periods=3).std().fillna(0).iloc[-1])
            bb_up_1h = sma20_1h + 2.0 * std20_1h

            fib_1h = calculate_fibonacci_bands(df_1h, current_price)
            upper_6_1h = float(fib_1h.get('upper_6') or 0.0)

            # A. Clímax Parabólico 1H In-Flight:
            # Si (OPEN > BB_Upper_1h o Precio > UPPER_6_1h o sin datos de UPPER_5/6),
            # y el tamaño en formación supera en un 70% el tamaño de la vela anterior de 1H con Precio > High_prev
            is_outside_bands_1h = (cur_o1h >= bb_up_1h * 0.99) or (upper_6_1h > 0 and current_price >= upper_6_1h * 0.99) or (upper_6_1h <= 0)
            is_70pct_expansion_1h = (cur_range1h >= 1.70 * prev_range1h) and (current_price > prev_h1h)

            if is_outside_bands_1h and is_70pct_expansion_1h and not partial_2_done:
                shares_sell = max(1, int(current_shares * 0.35))
                res.update({
                    'should_exit': True,
                    'action': 'PARTIAL_SELL_35',
                    'shares_to_sell': shares_sell,
                    'pct_to_sell': 35,
                    'rule_code': 'FT_PARTIAL_SELL',
                    'reason': (
                        f"Clímax Parabólico 1H: Vela en formación (${cur_range1h:.2f}) supera en +70% a la previa (${prev_range1h:.2f}) "
                        f"estando sobre BB Upper / UPPER_6. Venta parcial del 35% ({shares_sell} sh @ ${current_price:.2f})."
                    )
                })
                return res

            # B. Ruptura de OPEN de 1H en Rojo (Anti-Giveback):
            # Si la vela de 1H abrió arriba pero retrocede perdiendo su OPEN (current_price <= cur_o1h)
            # tras haber marcado un nuevo máximo relativo
            if cur_h1h > prev_h1h and current_price <= cur_o1h and gain_pct >= 2.0:
                shares_sell = max(1, int(current_shares * 0.30))
                res.update({
                    'should_exit': True,
                    'action': 'PARTIAL_SELL_30',
                    'shares_to_sell': shares_sell,
                    'pct_to_sell': 30,
                    'rule_code': 'FT_PARTIAL_SELL',
                    'reason': (
                        f"Rechazo en 1H: Precio (${current_price:.2f}) perforó a la baja su OPEN de 1H (${cur_o1h:.2f}) "
                        f"tras alcanzar High ${cur_h1h:.2f}. Protegiendo ganancias con venta parcial del 30%."
                    )
                })
                return res

            # C. UPPER_6 de 1H o RSI_1H >= 80
            from ta.momentum import RSIIndicator
            rsi_1h = float(RSIIndicator(c1h, window=14).rsi().iloc[-1]) if len(c1h) >= 14 else 50.0
            touched_upper6_1h = (upper_6_1h > 0 and current_price >= upper_6_1h * 0.998)
            if (touched_upper6_1h or rsi_1h >= 80.0) and not partial_1_done:
                shares_sell = max(1, int(current_shares * 0.40))
                res.update({
                    'should_exit': True,
                    'action': 'PARTIAL_SELL_40',
                    'shares_to_sell': shares_sell,
                    'pct_to_sell': 40,
                    'rule_code': 'FT_PARTIAL_SELL',
                    'reason': (
                        f"Extremo 1H alcanzado: UPPER_6 (${upper_6_1h:.2f}) o RSI_1H ({rsi_1h:.1f} >= 80). "
                        f"Cierre parcial 40% ({shares_sell} sh), remanente cabalgando con Trailing Stop."
                    )
                })
                return res

        except Exception as e_1h:
            log_warning(MODULE, f"Error en evaluación de salidas 1H: {e_1h}")

    return res


# -------------------------------------------------------------------------
# C. EVALUACIÓN DE RECOMPRA INTELIGENTE (SCALING-IN / PYRAMIDING)
# -------------------------------------------------------------------------
def evaluate_fast_track_reentry(
    position: dict,
    df_5m: Optional[pd.DataFrame],
    df_15m: Optional[pd.DataFrame],
    df_1h: Optional[pd.DataFrame],
    current_price: float,
    last_climax_exit_time: Optional[datetime] = None
) -> dict:
    """
    Evalúa la Recompra (Scaling-In / Pyramiding) para añadir a ganadores:
    - Candado Anti-Distribución: Prohibido recomprar si hubo venta parcial por clímax en los últimos 45 mins.
    - Candado Livermore: Solo recomprar si Precio Actual > Precio Compra Previo (promediar al alza).
    - Máximo 2 recompras acumuladas por ticker (Tranches: 30% Inicial + 35% Recompra 1 + 35% Recompra 2).
    - Condición 1 (Estructura): Low_15m > Low_15m_prev AND Low_1H > Low_1H_prev AND EMA3_15m > EMA9_15m.
      Gatillo 5m: Low_5m <= (EMA9_5m + Delta).
    - Condición 2 (Boca de Cocodrilo): BB_Upper_15m ascendente Y BB_Lower_15m descendente.
      Gatillo 5m: Low_5m <= (EMA9_5m + Delta).
    """
    res = {
        'should_reenter': False,
        'ticker': position.get('ticker'),
        'reentry_price': current_price,
        'tranche_pct': 0.35,
        'rule_code': 'NONE',
        'reason': '',
        'new_global_sl': 0.0
    }

    reentry_count = int(position.get('reentry_count') or 0)
    if reentry_count >= 2:
        res['reason'] = f"Límite máximo de recompras alcanzado ({reentry_count}/2)"
        return res

    avg_price = float(position.get('avg_price') or position.get('entry_price') or 0.0)
    # Candado Livermore: No promediar a la baja
    if current_price <= avg_price * 1.01:
        res['reason'] = f"Precio actual (${current_price:.2f}) no supera holgadamente el precio previo (${avg_price:.2f}); regla Pyramiding prohíbe promediar a la baja"
        return res

    # Candado Anti-Distribución: Si hubo un clímax reciente en los últimos 45 minutos, no recomprar
    if last_climax_exit_time is not None:
        mins_since_climax = (datetime.now(timezone.utc) - last_climax_exit_time).total_seconds() / 60.0
        if mins_since_climax < 45.0:
            res['reason'] = f"Candado Anti-Distribución activo: Clímax detectado hace {mins_since_climax:.1f}m (< 45m). Rechazo de recompra por riesgo de falso dip"
            return res

    if df_5m is None or len(df_5m) < 5 or df_15m is None or len(df_15m) < 3:
        res['reason'] = "Datos insuficientes de 5m o 15m para validar recompra"
        return res

    try:
        # Indicadores en 5m
        c5 = _safe_col(df_5m, 'close')
        l5 = _safe_col(df_5m, 'low')
        h5 = _safe_col(df_5m, 'high')
        ema9_5m = float(c5.ewm(span=9, adjust=False).mean().iloc[-1])
        delta_5m = max(0.04, round(ema9_5m * 0.008, 3))
        cur_l5 = float(l5.iloc[-1])

        # Gatillo en 5m: Low_5m toca o perfora ligeramente EMA9_5m (Pullback a la media rápida)
        pullback_5m_hit = (cur_l5 <= ema9_5m + delta_5m) and (current_price >= ema9_5m - delta_5m)

        if not pullback_5m_hit:
            res['reason'] = f"Low 5m (${cur_l5:.2f}) no ha tocado la zona de soporte EMA9_5m (${ema9_5m:.2f} + Delta ${delta_5m:.2f})"
            return res

        # -----------------------------------------------------------------
        # Condición 1: Estructura de Mínimos Crecientes 15m y 1H + Cruce EMA
        # -----------------------------------------------------------------
        l15 = _safe_col(df_15m, 'low')
        c15 = _safe_col(df_15m, 'close')
        ema3_15m = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
        ema9_15m = float(c15.ewm(span=9, adjust=False).mean().iloc[-1])
        prev_ema3_15m = float(c15.ewm(span=3, adjust=False).mean().iloc[-2])

        min_15m_growing = float(l15.iloc[-1]) > float(l15.iloc[-2]) if len(l15) >= 2 else True
        ema3_ascending_15m = (ema3_15m > ema9_15m) and (ema3_15m > prev_ema3_15m)

        min_1h_growing = True
        if df_1h is not None and len(df_1h) >= 2:
            l1h = _safe_col(df_1h, 'low')
            min_1h_growing = float(l1h.iloc[-1]) > float(l1h.iloc[-2])

        condition_1_met = min_15m_growing and min_1h_growing and ema3_ascending_15m

        # -----------------------------------------------------------------
        # Condición 2: Expansión de Bandas de Bollinger 15m (Boca de Cocodrilo)
        # -----------------------------------------------------------------
        sma20_15 = c15.rolling(20, min_periods=5).mean()
        std20_15 = c15.rolling(20, min_periods=5).std().fillna(0)
        bb_up_15 = sma20_15 + 2.0 * std20_15
        bb_lo_15 = sma20_15 - 2.0 * std20_15

        bb_up_slope = float(bb_up_15.iloc[-1] - bb_up_15.iloc[-2])
        bb_lo_slope = float(bb_lo_15.iloc[-1] - bb_lo_15.iloc[-2])
        alligator_mouth_expanding = (bb_up_slope > 0.0) and (bb_lo_slope < 0.0)

        condition_2_met = alligator_mouth_expanding

        if condition_1_met or condition_2_met:
            # Nuevo Stop Loss Global: Proteger a Break-Even global (Riesgo Cero) o nuevo EMA9_15m - Delta
            delta_15m = calculate_fast_track_delta(df_15m, ema9_15m)
            proposed_global_sl = max(avg_price, round(ema9_15m - delta_15m, 2))

            rule = "FT_REENTRY_BUY"
            res.update({
                'should_reenter': True,
                'reentry_price': current_price,
                'tranche_pct': 0.35,
                'rule_code': rule,
                'new_global_sl': proposed_global_sl,
                'reason': (
                    f"Recompra Pyramiding ({reentry_count+1}/2) validada por {rule}: "
                    f"Pullback en 5m a EMA9 (${ema9_5m:.2f}), "
                    f"Estructura 15m/1H {'Mínimos Crecientes' if condition_1_met else 'Boca Bollinger Abierta'}. "
                    f"Stop Global elevado a ${proposed_global_sl:.2f} (Riesgo Cero)."
                )
            })
            return res

        res['reason'] = "Pullback en 5m sin confirmación estructural de 15m (ni mínimos crecientes ni bandas expandidas)"
        return res

    except Exception as e_re:
        log_error(MODULE, f"Error evaluando recompra para {position.get('ticker')}: {e_re}")
        res['reason'] = str(e_re)
        return res
