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

        # 2. Filtro de Volumen y Combustible Inicial
        vol_ma = float(v5.rolling(10, min_periods=2).mean().iloc[-1]) if len(v5) >= 2 else cur_v
        rvol_5m = (cur_v / vol_ma) if vol_ma > 0 else 1.0

        first_v = float(v5.iloc[0])
        first_c = float(c5.iloc[0])
        first_o = float(o5.iloc[0])
        first_candle_tsunami = (first_v >= 1_000_000) or (first_v >= 500_000 and first_c >= first_o)

        # Si el gap es extremo (> +50%):
        # A. Si la 1ra vela acumuló un Tsunami Institucional (>= 1M sh) o la 2da vela abre con gap sobre la 1ra (Open >= Close_1),
        #    se autoriza la compra inmediata en el OPEN de la 2da vela (08:35 AM) sin esperar su cierre.
        # B. En caso contrario, exigir confirmación ORB clásica (2da vela rompe High previo).
        if gap_pct > 50.0:
            if len(df_5m) >= 2:
                prev_h = float(h5.iloc[-2])
                second_candle_open_gap = (cur_o >= float(c5.iloc[-2]) * 0.998)
                if first_candle_tsunami and (cur_c >= float(c5.iloc[-2]) * 0.98 or second_candle_open_gap):
                    # Tsunami de volumen confirmado al Open: Compra autorizada inmediatamente
                    pass
                elif cur_c <= prev_h:
                    res['reason'] = f"Gap parabólico ({gap_pct:.1f}% > 50%): Esperando confirmación ORB-5m (Close ${cur_c:.2f} <= High previo ${prev_h:.2f})"
                    return res
            else:
                if not (first_candle_tsunami and cur_c >= cur_o):
                    res['reason'] = f"Gap parabólico ({gap_pct:.1f}% > 50%): Esperar 2da vela o volumen tsunami >= 1M"
                    return res

        has_massive_vol = (cur_v >= 250_000) or (rvol_5m >= 2.0) or first_candle_tsunami or (cur_v * cur_c >= 1_000_000)
        if not has_massive_vol:
            res['reason'] = f"Volumen 5m insuficiente ({cur_v:,.0f} sh, RVOL={rvol_5m:.1f}x < 2.0x)"
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
            # SALIDA 3 (EXTREMO PARABÓLICO): RSI_15m >= 85 -> CIERRE TOTAL 100%
            # -----------------------------------------------------------------
            # Si el RSI supera los 85, es un agotamiento comprador extremo (Blow-Off Top).
            # Se cierra el 100% incondicionalmente para amarrar la ganancia en la cima.
            from ta.momentum import RSIIndicator
            rsi_15m = float(RSIIndicator(c15, window=14).rsi().iloc[-1]) if len(c15) >= 14 else 50.0

            if rsi_15m >= 85.0 and gain_pct >= 6.0:
                res.update({
                    'should_exit': True,
                    'action': 'FULL_EXIT',
                    'shares_to_sell': current_shares,
                    'pct_to_sell': 100,
                    'rule_code': 'FT_CLIMAX_EXTREME_RSI85',
                    'reason': (
                        f"🚀 SALIDA 3 - CLÍMAX EXTREMO: RSI 15m ({rsi_15m:.1f} >= 85.0). "
                        f"Agotamiento comprador máximo (Blow-off Top). Cierre TOTAL 100% ({current_shares} sh @ ${current_price:.2f}, +{gain_pct:.1f}%)."
                    )
                })
                return res

            # Bollinger Bands 15m
            sma20_15 = float(c15.rolling(20, min_periods=5).mean().iloc[-1])
            std20_15 = float(c15.rolling(20, min_periods=5).std().fillna(0).iloc[-1])
            bb_up_15 = sma20_15 + 2.0 * std20_15

            cur_h15 = max(float(h15.iloc[-1]), current_price)
            cur_l15 = min(float(l15.iloc[-1]), current_price)
            cur_o15 = float(o15.iloc[-1])
            cur_c15 = current_price
            cur_range15 = max(1e-6, cur_h15 - cur_l15)

            fib_15m = calculate_fibonacci_bands(df_15m, current_price)
            upper_6_15m = float(fib_15m.get('upper_6') or 0.0)

            outside_bb15 = (cur_c15 >= bb_up_15 * 0.995) or (cur_h15 >= bb_up_15)
            touched_upper6 = (upper_6_15m > 0 and current_price >= upper_6_15m * 0.995)

            # Comparar tamaño con las 9 velas anteriores de 15m
            prev_9_ranges = (h15.iloc[-10:-1] - l15.iloc[-10:-1]).values if len(h15) >= 10 else []
            avg_9_rng = float(np.mean(prev_9_ranges)) if len(prev_9_ranges) > 0 else 0.0
            is_2x_expansion = (avg_9_rng > 0 and cur_range15 >= 2.0 * avg_9_rng)

            upper_wick = cur_h15 - max(cur_o15, cur_c15)
            upper_wick_pct = upper_wick / cur_range15

            # -----------------------------------------------------------------
            # SALIDA 1: CLÍMAX INICIAL (RSI >= 80, UPPER_6 o BB_UPPER) -> VENTA PARCIAL 50%
            # -----------------------------------------------------------------
            is_climax_15m = (rsi_15m >= 80.0) or (is_2x_expansion and upper_wick_pct >= 0.10 and outside_bb15) or touched_upper6
            if not partial_1_done and is_climax_15m and gain_pct >= 6.0 and current_shares >= 2:
                shares_sell = max(1, int(current_shares * 0.50))
                # Elevar Trailing Ratchet de inmediato al Low de la vela de clímax o EMA3
                ema3_15_val = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
                climax_ratchet_sl = max(cur_sl, round(min(cur_l15, ema3_15_val), 2))
                res.update({
                    'should_exit': True,
                    'action': 'PARTIAL_SELL_50',
                    'shares_to_sell': shares_sell,
                    'pct_to_sell': 50,
                    'rule_code': 'FT_PARTIAL_SELL_CLIMAX',
                    'should_update_sl': True,
                    'new_stop_loss': climax_ratchet_sl,
                    'sl_reason': f"Trailing Ratchet Clímax elevado a ${climax_ratchet_sl:.2f} (Low Clímax / EMA3)",
                    'reason': (
                        f"🎯 SALIDA 1 - CLÍMAX INICIAL: RSI 15m={rsi_15m:.1f} (>=80), BB_Upper=${bb_up_15:.2f}. "
                        f"Venta Parcial 50% ({shares_sell} sh @ ${current_price:.2f}, +{gain_pct:.1f}%). Stop del remanente ceñido a ${climax_ratchet_sl:.2f}."
                    )
                })
                return res

            # -----------------------------------------------------------------
            # SALIDA 2: RANGE DECAY / CONTRACCIÓN DE RANGO POST-CLÍMAX -> CIERRE TOTAL REMANENTE
            # -----------------------------------------------------------------
            # Si ya se ejecutó la Venta Parcial 50%, vigilar la siguiente vela de 15m:
            # Si el rango de la vela se contrae (< 75% de la vela de clímax) y muestra rechazo o rompe su Open/Low/EMA3
            if partial_1_done and len(h15) >= 2:
                prev_rng15 = max(1e-6, float(h15.iloc[-2]) - float(l15.iloc[-2]))
                range_ratio = cur_range15 / prev_rng15
                is_range_decay = (range_ratio < 0.75) and (cur_c15 <= cur_o15 * 0.998 or cur_l15 < float(l15.iloc[-2]) or upper_wick_pct >= 0.20)
                ema3_15_now = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
                lost_ema3 = (cur_c15 < ema3_15_now * 0.995)

                if is_range_decay or lost_ema3:
                    res.update({
                        'should_exit': True,
                        'action': 'FULL_EXIT',
                        'shares_to_sell': current_shares,
                        'pct_to_sell': 100,
                        'rule_code': 'FT_RANGE_DECAY_EXIT',
                        'reason': (
                            f"🛑 SALIDA 2 - CONTRACCIÓN DE RANGO (Range Decay): Rango 15m (${cur_range15:.2f}) < 75% del previo (${prev_rng15:.2f}) "
                            f"con rechazo/pérdida de EMA3 (${ema3_15_now:.2f}). Cierre TOTAL remanente ({current_shares} sh @ ${current_price:.2f}, +{gain_pct:.1f}%)."
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
        # Validación de Seguridad Macro 1H (SIPV, Ángulo EMA3 y Rango)
        # -----------------------------------------------------------------
        if df_1h is not None and len(df_1h) >= 3:
            c1h = _safe_col(df_1h, 'close')
            o1h = _safe_col(df_1h, 'open')
            h1h = _safe_col(df_1h, 'high')
            l1h = _safe_col(df_1h, 'low')

            # 1. Ángulo de la EMA3 en 1H (Debe ser estrictamente ascendente)
            ema3_1h = c1h.ewm(span=3, adjust=False).mean()
            slope_ema3_1h = float(ema3_1h.iloc[-1] - ema3_1h.iloc[-2])
            if slope_ema3_1h <= 0.0:
                res['reason'] = f"Ángulo de EMA3 en 1H plano o descendente ({slope_ema3_1h:+.4f}). Agotamiento macro, recompra prohibida."
                return res

            # 2. Análisis de Mechas SIPV en Vela 1H Viva
            cur_h1h = max(float(h1h.iloc[-1]), current_price)
            cur_l1h = min(float(l1h.iloc[-1]), current_price)
            cur_rng1h = max(1e-6, cur_h1h - cur_l1h)
            cur_o1h = float(o1h.iloc[-1])
            top_body1h = max(cur_o1h, current_price)
            upper_wick_ratio_1h = (cur_h1h - top_body1h) / cur_rng1h

            if upper_wick_ratio_1h >= 0.35:
                res['reason'] = f"Rechazo SIPV en 1H: Mecha superior {upper_wick_ratio_1h*100:.1f}% >= 35%. Venta institucional en techo, recompra cancelada."
                return res

            # 3. Regla de Compresión de Rango de Vela en 1H (Desaceleración)
            prev_rng1h = max(1e-6, float(h1h.iloc[-2]) - float(l1h.iloc[-2]))
            range_compression_ratio = cur_rng1h / prev_rng1h
            if range_compression_ratio < 0.60 and current_price < float(h1h.iloc[-2]):
                res['reason'] = f"Veto por Compresión de Rango 1H: Rango actual (${cur_rng1h:.2f}) < 60% del previo (${prev_rng1h:.2f}). Pérdida de empuje comprador."
                res['is_range_compressed_exhaustion'] = True
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


# -------------------------------------------------------------------------
# D. EVALUACIÓN DE RE-IGNICIÓN DE SEGUNDA OLA (LEG-2 REVERSAL BREAKOUT)
# -------------------------------------------------------------------------
def evaluate_leg2_reversal_entry(
    ticker: str,
    df_5m: Optional[pd.DataFrame],
    df_15m: Optional[pd.DataFrame],
    df_1h: Optional[pd.DataFrame],
    current_price: float,
    current_time_et: Optional[datetime] = None,
    config: Optional[dict] = None
) -> dict:
    """
    Evalúa el Volteo de Mercado / Re-Ignición de Segunda Ola (Leg-2 Reversal):
    Detecta cuando un Super-Runner o Alpha Runner que sufrió una fuerte corrección
    (donde en 5m/15m EMA3 estuvo < EMA9 en fase bajista) vuelve a voltear al alza.

    Condiciones Estructurales:
    1. Gráfico 1H: EMA3_1h > EMA9_1h estrictamente (tendencia macro institucional intacta).
    2. Volteo de Mercado en 15m y 5m:
       - En 15m: EMA3_15m cruza por encima de EMA9_15m (EMA3_now > EMA9_now) tras haber estado
         por debajo en velas anteriores (EMA3_prev <= EMA9_prev o en las últimas 3-5 velas).
       - Pendiente EMA3_15m positiva (> 0).
       - En 5m: Vela verde actual sobre EMA9_5m y EMA3_5m > EMA9_5m.
    3. Volumen de Re-Ignición:
       - Volumen de 5m >= 200,000 acciones o RVOL_5m >= 2.0x o (Volumen_5m * Precio >= $1,000,000 USD).
    4. Tranche: Asignación estándar de Runner (35% inicial con piramidación disponible).
    """
    res = {
        'is_valid': False,
        'ticker': ticker,
        'entry_price': current_price,
        'initial_stop_loss': 0.0,
        'position_tranche_pct': 0.35,
        'rule_code': 'NONE',
        'reason': ''
    }

    if df_5m is None or len(df_5m) < 3 or df_15m is None or len(df_15m) < 3:
        res['reason'] = "Datos insuficientes de 5m o 15m para validar Leg-2 Reversal"
        return res

    try:
        # 1. Macro-Tendencia en 1H: EMA3_1h > EMA9_1h
        if df_1h is not None and len(df_1h) >= 2:
            c1h = _safe_col(df_1h, 'close')
            ema3_1h = float(c1h.ewm(span=3, adjust=False).mean().iloc[-1])
            ema9_1h = float(c1h.ewm(span=9, adjust=False).mean().iloc[-1])
            if ema3_1h <= ema9_1h:
                res['reason'] = f"Macro 1H bajista o neutral (EMA3 ${ema3_1h:.2f} <= EMA9 ${ema9_1h:.2f}). No califica para Leg-2 Reversal."
                return res

        # 2. Volteo en 15m: EMA3 cruza por encima de EMA9 tras haber estado por debajo
        c15 = _safe_col(df_15m, 'close')
        l15 = _safe_col(df_15m, 'low')
        ema3_15_series = c15.ewm(span=3, adjust=False).mean()
        ema9_15_series = c15.ewm(span=9, adjust=False).mean()

        ema3_15_now = float(ema3_15_series.iloc[-1])
        ema9_15_now = float(ema9_15_series.iloc[-1])

        # Verificar si actualmente EMA3 > EMA9 en 15m
        if ema3_15_now <= ema9_15_now:
            res['reason'] = f"15m aún no voltea: EMA3 (${ema3_15_now:.2f}) <= EMA9 (${ema9_15_now:.2f})"
            return res

        # Verificar si en las últimas 1 a 5 velas estuvo por debajo (es un giro fresco / volteo)
        was_below_recently = False
        lookback_15 = min(6, len(ema3_15_series))
        for k in range(2, lookback_15 + 1):
            if float(ema3_15_series.iloc[-k]) <= float(ema9_15_series.iloc[-k]) * 1.002:
                was_below_recently = True
                break

        if not was_below_recently:
            res['reason'] = "15m no presenta cruce reciente de volteo (no viene de EMA3 < EMA9)"
            return res

        # 3. Confirmación en 5m
        c5 = _safe_col(df_5m, 'close')
        o5 = _safe_col(df_5m, 'open')
        l5 = _safe_col(df_5m, 'low')
        v5 = _safe_col(df_5m, 'volume')

        cur_c5 = float(c5.iloc[-1])
        cur_o5 = float(o5.iloc[-1])
        cur_l5 = float(l5.iloc[-1])
        cur_v5 = float(v5.iloc[-1])

        ema3_5m = float(c5.ewm(span=3, adjust=False).mean().iloc[-1])
        ema9_5m = float(c5.ewm(span=9, adjust=False).mean().iloc[-1])

        if ema3_5m <= ema9_5m or cur_c5 < cur_o5 * 0.995:
            res['reason'] = f"5m no confirma empuje: EMA3 (${ema3_5m:.2f}) vs EMA9 (${ema9_5m:.2f}) o vela roja"
            return res

        # 4. Volumen de Combustible en la Re-Ignición
        vol_ma5 = float(v5.rolling(10, min_periods=2).mean().iloc[-1]) if len(v5) >= 2 else cur_v5
        rvol_5m = (cur_v5 / vol_ma5) if vol_ma5 > 0 else 1.0
        has_volume = (cur_v5 >= 200_000) or (rvol_5m >= 1.8) or (cur_v5 * cur_c5 >= 1_000_000)

        if not has_volume:
            res['reason'] = f"Volumen 5m insuficiente en la re-ignición ({cur_v5:,.0f} sh, RVOL={rvol_5m:.1f}x < 1.8x)"
            return res

        # 5. Stop Loss Ceñido al Low del Giro
        min_reversal_low = min(float(l15.iloc[-1]), float(l5.iloc[-1]), float(l5.iloc[-2]) if len(l5) >= 2 else cur_l5)
        init_sl = round(min_reversal_low * 0.985, 2)
        if init_sl >= current_price or init_sl <= 0:
            init_sl = round(current_price * 0.95, 2)

        res.update({
            'is_valid': True,
            'entry_price': current_price,
            'initial_stop_loss': init_sl,
            'position_tranche_pct': 0.35,
            'rule_code': 'FT_RUNNER_REVERSAL_LEG2',
            'reason': (
                f"Volteo Alcista OLA 2 (Leg-2 Reversal): 1H alcista (EMA3 > EMA9), 15m volteó a EMA3 (${ema3_15_now:.2f}) > "
                f"EMA9 (${ema9_15_now:.2f}) tras caída previa. 5m con {cur_v5:,.0f} sh (RVOL {rvol_5m:.1f}x). Stop=${init_sl:.2f}."
            )
        })
        return res

    except Exception as e_l2:
        log_error(MODULE, f"Error evaluando Leg-2 Reversal para {ticker}: {e_l2}")
        res['reason'] = str(e_l2)
        return res

