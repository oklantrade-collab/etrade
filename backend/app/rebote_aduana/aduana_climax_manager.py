"""
ADUANAS Multi-TF Fibonacci Climax Manager — Cierre Parcial Adaptativo y Blindaje Break-Even
Mercados: Crypto Futures (Binance) & Forex (IC Markets / cTrader)
Temporalidades: 5m, 15m, 1h, 4h, 1d
"""

import math
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from app.core.logger import log_info, log_warning, log_error
from app.analysis.fibonacci_bb import extract_fib_levels, fibonacci_bollinger

MODULE = "ADUANA_CLIMAX"

class AduanaClimaxManager:
    """
    Gestiona la detección de clímax institucional en bandas Fibonacci (5 y 6)
    a través de múltiples temporalidades con escalado de lote adaptativo
    y blindaje mandatorio de Stop Loss a Break-Even.
    """

    MIN_PROFIT_PCT_CRYPTO_5M  = 0.40  # +0.40% en 5m (atrapa mechas de scalping/absorción rápida)
    MIN_PROFIT_PCT_CRYPTO_15M = 0.50  # +0.50% en 15m (mayor desarrollo y recorrido estructural)

    MIN_PROFIT_PIPS_FOREX_5M  = 5.0   # +5.0 pips en 5m
    MIN_PROFIT_PIPS_FOREX_15M = 7.0   # +7.0 pips en 15m

    BUFFER_BE_PCT_CRYPTO  = 0.0015  # 0.15% sobre/bajo entrada para comisiones Taker
    BUFFER_BE_PIPS_FOREX  = 2.0     # 2.0 pips sobre/bajo entrada para spread/comisión

    @staticmethod
    def calculate_pnl(pos: dict, current_price: float) -> Tuple[float, float]:
        """
        Calcula el PnL actual en porcentaje (%) y en pips (para Forex).
        Returns: (pnl_pct, pips)
        """
        entry = float(pos.get('avg_entry_price') or pos.get('entry_price') or 0.0)
        if entry <= 0:
            return 0.0, 0.0

        side = (pos.get('side') or '').lower()
        is_long = side in ('long', 'buy')
        symbol = str(pos.get('symbol') or '').upper()

        if is_long:
            pnl_pct = (current_price - entry) / entry * 100.0
        else:
            pnl_pct = (entry - current_price) / entry * 100.0

        # Pip calculation for Forex
        pips = 0.0
        pip_sz = 0.01 if ('JPY' in symbol or 'XAU' in symbol) else 0.0001
        if is_long:
            pips = (current_price - entry) / pip_sz
        else:
            pips = (entry - current_price) / pip_sz

        return round(pnl_pct, 4), round(pips, 2)

    @classmethod
    def get_timeframe_bands(cls, symbol: str, timeframe: str, memory_store: dict = None) -> Optional[dict]:
        """
        Obtiene las bandas Fibonacci (upper_5, upper_6, lower_5, lower_6, etc.)
        para una temporalidad específica desde MEMORY_STORE.
        """
        try:
            from app.core.memory_store import get_memory_df, MEMORY_STORE
            df = None
            if memory_store and symbol in memory_store and timeframe in memory_store[symbol]:
                df = memory_store[symbol][timeframe].get('df')
            if df is None:
                df = get_memory_df(symbol, timeframe)

            if df is None or len(df) < 5:
                return None

            # Si ya tiene bandas calculadas
            if 'lower_5' in df.columns and 'upper_5' in df.columns:
                last_row = df.iloc[-1]
                return {
                    'upper_5': float(last_row.get('upper_5', 0)),
                    'upper_6': float(last_row.get('upper_6', 0)),
                    'lower_5': float(last_row.get('lower_5', 0)),
                    'lower_6': float(last_row.get('lower_6', 0)),
                    'basis': float(last_row.get('basis', 0))
                }

            # Si no las tiene, calcularlas
            df_fib = fibonacci_bollinger(df, length=min(len(df), 200), mult=3.0)
            last_fib = df_fib.iloc[-1]
            return {
                'upper_5': float(last_fib.get('upper_5', 0)),
                'upper_6': float(last_fib.get('upper_6', 0)),
                'lower_5': float(last_fib.get('lower_5', 0)),
                'lower_6': float(last_fib.get('lower_6', 0)),
                'basis': float(last_fib.get('basis', 0))
            }
        except Exception as e:
            log_warning(MODULE, f"Error obteniendo bandas {timeframe} para {symbol}: {e}")
            return None

    @classmethod
    def check_macro_confluence(
        cls,
        symbol: str,
        target_direction: str,
        current_price: float,
        memory_store: dict = None
    ) -> Tuple[bool, str]:
        """
        Evalúa si la temporalidad macro (1h y/o 4h) presenta confluencia de soporte/resistencia
        o cambio de sesgo que justifique el CIERRE 100% de la posición actual y GIRO (SAR).

        Para target_direction == 'long' (anticipando rebote alcista):
        - 1h o 4h tiene EMA3 creciente / positiva (slope > 0)
        - 1h o 4h tiene EMA3 > EMA9
        - 1h o 4h tiene precio testeando o rebotando en Banda Inferior de Bollinger
        - 1h o 4h tiene vela verde de giro o mecha inferior >= 25%

        Para target_direction == 'short' (anticipando rebote bajista):
        - 1h o 4h tiene EMA3 decreciente / negativa (slope < 0)
        - 1h o 4h tiene EMA3 < EMA9
        - 1h o 4h tiene precio testeando o rebotando en Banda Superior de Bollinger
        - 1h o 4h tiene vela roja de giro o mecha superior >= 25%
        """
        try:
            from app.core.memory_store import get_memory_df
            df_1h = None
            df_4h = None
            if memory_store and symbol in memory_store:
                df_1h = memory_store[symbol].get('1h', {}).get('df')
                df_4h = memory_store[symbol].get('4h', {}).get('df')
            if df_1h is None:
                df_1h = get_memory_df(symbol, '1h')
            if df_4h is None:
                df_4h = get_memory_df(symbol, '4h')

            is_target_long = str(target_direction).lower() in ('long', 'buy')
            reasons = []

            # ── EVALUAR 1 HORA ──
            if df_1h is not None and not df_1h.empty and len(df_1h) >= 3:
                closes_1h = df_1h['close'].astype(float)
                ema3_1h = closes_1h.ewm(span=3, adjust=False).mean()
                ema9_1h = closes_1h.ewm(span=9, adjust=False).mean()

                e3_now = float(ema3_1h.iloc[-1])
                e3_prev = float(ema3_1h.iloc[-2])
                e9_now = float(ema9_1h.iloc[-1])
                slope_1h = (e3_now - e3_prev) / e3_prev * 100.0 if e3_prev > 0 else 0.0

                sma20_1h = closes_1h.rolling(min(len(closes_1h), 20)).mean().iloc[-1]
                std20_1h = closes_1h.rolling(min(len(closes_1h), 20)).std().iloc[-1]
                lower_bb_1h = sma20_1h - (2.0 * std20_1h) if not pd.isna(std20_1h) else 0.0
                upper_bb_1h = sma20_1h + (2.0 * std20_1h) if not pd.isna(std20_1h) else 0.0

                last_row_1h = df_1h.iloc[-1]
                o_1h = float(last_row_1h.get('open', 0))
                h_1h = float(last_row_1h.get('high', 0))
                l_1h = float(last_row_1h.get('low', 0))
                c_1h = float(last_row_1h.get('close', 0))
                rng_1h = h_1h - l_1h

                if is_target_long:
                    if slope_1h > 0:
                        reasons.append(f"1h EMA3 alcista (+{slope_1h:.2f}%)")
                    if e3_now > e9_now:
                        reasons.append(f"1h EMA3>EMA9")
                    if lower_bb_1h > 0 and (current_price <= lower_bb_1h * 1.002 or l_1h <= lower_bb_1h * 1.002):
                        reasons.append(f"1h soporte Lower BB ({lower_bb_1h:.4f})")
                    if rng_1h > 0:
                        lower_wick_1h = (min(o_1h, c_1h) - l_1h) / rng_1h
                        if lower_wick_1h >= 0.25 or c_1h > o_1h:
                            reasons.append(f"1h rechazo mecha/verde ({lower_wick_1h:.0%})")
                else:
                    if slope_1h < 0:
                        reasons.append(f"1h EMA3 bajista ({slope_1h:.2f}%)")
                    if e3_now < e9_now:
                        reasons.append(f"1h EMA3<EMA9")
                    if upper_bb_1h > 0 and (current_price >= upper_bb_1h * 0.998 or h_1h >= upper_bb_1h * 0.998):
                        reasons.append(f"1h resistencia Upper BB ({upper_bb_1h:.4f})")
                    if rng_1h > 0:
                        upper_wick_1h = (h_1h - max(o_1h, c_1h)) / rng_1h
                        if upper_wick_1h >= 0.25 or c_1h < o_1h:
                            reasons.append(f"1h rechazo mecha/rojo ({upper_wick_1h:.0%})")

            # ── EVALUAR 4 HORAS ──
            if df_4h is not None and not df_4h.empty and len(df_4h) >= 3:
                closes_4h = df_4h['close'].astype(float)
                ema3_4h = closes_4h.ewm(span=3, adjust=False).mean()
                ema9_4h = closes_4h.ewm(span=9, adjust=False).mean()

                e3_4h_now = float(ema3_4h.iloc[-1])
                e3_4h_prev = float(ema3_4h.iloc[-2])
                e9_4h_now = float(ema9_4h.iloc[-1])
                slope_4h = (e3_4h_now - e3_4h_prev) / e3_4h_prev * 100.0 if e3_4h_prev > 0 else 0.0

                sma20_4h = closes_4h.rolling(min(len(closes_4h), 20)).mean().iloc[-1]
                std20_4h = closes_4h.rolling(min(len(closes_4h), 20)).std().iloc[-1]
                lower_bb_4h = sma20_4h - (2.0 * std20_4h) if not pd.isna(std20_4h) else 0.0
                upper_bb_4h = sma20_4h + (2.0 * std20_4h) if not pd.isna(std20_4h) else 0.0

                if is_target_long:
                    if slope_4h > 0:
                        reasons.append(f"4h EMA3 alcista (+{slope_4h:.2f}%)")
                    if e3_4h_now > e9_4h_now:
                        reasons.append(f"4h EMA3>EMA9")
                    if lower_bb_4h > 0 and current_price <= lower_bb_4h * 1.003:
                        reasons.append(f"4h soporte Lower BB ({lower_bb_4h:.4f})")
                else:
                    if slope_4h < 0:
                        reasons.append(f"4h EMA3 bajista ({slope_4h:.2f}%)")
                    if e3_4h_now < e9_4h_now:
                        reasons.append(f"4h EMA3<EMA9")
                    if upper_bb_4h > 0 and current_price >= upper_bb_4h * 0.997:
                        reasons.append(f"4h resistencia Upper BB ({upper_bb_4h:.4f})")

            if reasons:
                return True, " | ".join(reasons)
            return False, "Sin confluencia macro de soporte/resistencia"
        except Exception as e:
            return False, f"Error en confluencia macro: {e}"

    @classmethod
    def evaluate_climax_sipv_signal(
        cls,
        symbol: str,
        direction: str,
        current_price: float,
        memory_store: dict = None,
        is_sar: bool = False,
        climax_extreme: Optional[float] = None
    ) -> dict:
        """
        Evalúa si procede una entrada LONG o SHORT por REBOTE + SIPV en zona extrema (LOWER_5/6 o UPPER_5/6).
        Aplica tanto para GIRO (SAR tras cierre 100%) como para mercado FLAT (sin posición previa).
        """
        result = {'triggered': False, 'direction': direction}
        if not symbol or current_price <= 0:
            result['reason'] = "Parámetros inválidos"
            return result

        try:
            from app.core.memory_store import get_memory_df
            df_15m = None
            df_5m = None
            if memory_store and symbol in memory_store:
                df_15m = memory_store[symbol].get('15m', {}).get('df')
                df_5m = memory_store[symbol].get('5m', {}).get('df')
            if df_15m is None:
                df_15m = get_memory_df(symbol, '15m')
            if df_5m is None:
                df_5m = get_memory_df(symbol, '5m')

            if df_15m is None or df_15m.empty or len(df_15m) < 3:
                result['reason'] = "Datos insuficientes en 15m"
                return result

            is_long = str(direction).lower() in ('long', 'buy')
            dir_str = 'long' if is_long else 'short'
            bands_15m = cls.get_timeframe_bands(symbol, '15m', memory_store) or {}
            bands_5m = cls.get_timeframe_bands(symbol, '5m', memory_store) or {}

            # 1. Verificar toque de banda extrema (LOWER_5/6 para LONG o UPPER_5/6 para SHORT)
            l5_15 = bands_15m.get('lower_5', 0)
            l5_5m = bands_5m.get('lower_5', 0)
            u5_15 = bands_15m.get('upper_5', 0)
            u5_5m = bands_5m.get('upper_5', 0)

            c_low_15 = float(df_15m['low'].tail(2).min()) if len(df_15m) >= 2 else current_price
            c_high_15 = float(df_15m['high'].tail(2).max()) if len(df_15m) >= 2 else current_price

            if is_long:
                touched_band = (
                    (l5_15 > 0 and (current_price <= l5_15 * 1.0015 or c_low_15 <= l5_15 * 1.0015)) or
                    (l5_5m > 0 and (current_price <= l5_5m * 1.0015 or c_low_15 <= l5_5m * 1.0015)) or
                    (climax_extreme is not None and l5_15 > 0 and climax_extreme <= l5_15 * 1.002)
                )
            else:
                touched_band = (
                    (u5_15 > 0 and (current_price >= u5_15 * 0.9985 or c_high_15 >= u5_15 * 0.9985)) or
                    (u5_5m > 0 and (current_price >= u5_5m * 0.9985 or c_high_15 >= u5_5m * 0.9985)) or
                    (climax_extreme is not None and u5_15 > 0 and climax_extreme >= u5_15 * 0.998)
                )

            # Si es SAR (recién salimos en clímax), se asume toque confirmado
            if is_sar:
                touched_band = True

            if not touched_band:
                result['reason'] = f"Precio fuera de zona extrema clímax 5/6 ({'LOWER' if is_long else 'UPPER'})"
                return result

            # 2. Confluencia Macro (1h / 4h)
            macro_ok, macro_reason = cls.check_macro_confluence(symbol, dir_str, current_price, memory_store)
            if not macro_ok:
                result['reason'] = f"Sin confluencia macro constructiva ({macro_reason})"
                return result

            # 3. Filtro Cuchillo Cayendo / Mecha de Absorción (_check_wick_rejection)
            target_df = df_5m if (df_5m is not None and not df_5m.empty and len(df_5m) >= 2) else df_15m
            last_c = target_df.iloc[-1]
            o = float(last_c.get('open', 0))
            h = float(last_c.get('high', 0))
            l = float(last_c.get('low', 0))
            c = float(last_c.get('close', 0))
            rng = h - l

            if rng > 0:
                if is_long:
                    wick = min(o, c) - l
                    wick_ratio = wick / rng
                    is_reversal = (wick_ratio >= 0.25) or (c > o)
                else:
                    wick = h - max(o, c)
                    wick_ratio = wick / rng
                    is_reversal = (wick_ratio >= 0.25) or (c < o)
            else:
                is_reversal = True
                wick_ratio = 0.0

            # Si la última vela aún se forma, comprobar vela anterior
            if not is_reversal and len(target_df) >= 2:
                prev_c = target_df.iloc[-2]
                po = float(prev_c.get('open', 0))
                ph = float(prev_c.get('high', 0))
                pl = float(prev_c.get('low', 0))
                pc = float(prev_c.get('close', 0))
                prng = ph - pl
                if prng > 0:
                    if is_long:
                        pwick = min(po, pc) - pl
                        if (pwick / prng >= 0.25) or (pc > po):
                            is_reversal = True
                    else:
                        pwick = ph - max(po, pc)
                        if (pwick / prng >= 0.25) or (pc < po):
                            is_reversal = True

            if not is_reversal:
                result['reason'] = f"Filtro cuchillo cayendo no superado: mecha ({wick_ratio:.1%}) < 25% y sin vela de giro"
                return result

            # 4. Confirmación SIPV (Higher Lows o Cruce EMA3)
            closes_15 = df_15m['close'].astype(float)
            ema3_15 = float(closes_15.ewm(span=3, adjust=False).mean().iloc[-1])
            c_15 = float(df_15m['close'].iloc[-1])

            if is_long:
                sipv_ok = (c_15 >= ema3_15 * 0.9995)
                if not sipv_ok and len(df_15m) >= 3:
                    l0 = float(df_15m['low'].iloc[-1])
                    l1 = float(df_15m['low'].iloc[-2])
                    sipv_ok = (l0 >= l1 * 0.9995) or (c > o)
            else:
                sipv_ok = (c_15 <= ema3_15 * 1.0005)
                if not sipv_ok and len(df_15m) >= 3:
                    h0 = float(df_15m['high'].iloc[-1])
                    h1 = float(df_15m['high'].iloc[-2])
                    sipv_ok = (h0 <= h1 * 1.0005) or (c < o)

            if not sipv_ok:
                result['reason'] = "Estructura SIPV pendiente: falta confirmación de giro en EMA3/Higher Low"
                return result

            # 5. Cálculo de Stop Loss y Take Profit
            is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF', 'NZD'))
            pip_sz = 0.01 if ('JPY' in symbol or 'XAU' in symbol) else 0.0001
            rule_code = 'REB_CLIMAX_SAR' if is_sar else 'REB_CLIMAX_DIRECT'

            if is_long:
                ref_low = min(current_price, climax_extreme if climax_extreme else current_price, l)
                sl = round(ref_low - (3.0 * pip_sz), 5) if is_forex else round(ref_low * 0.998, 4)
                tp_ref = bands_15m.get('basis', 0)
                tp = round(tp_ref if tp_ref > current_price else (current_price + 20.0 * pip_sz), 5) if is_forex else round(tp_ref if tp_ref > current_price else (current_price * 1.015), 4)
            else:
                ref_high = max(current_price, climax_extreme if climax_extreme else current_price, h)
                sl = round(ref_high + (3.0 * pip_sz), 5) if is_forex else round(ref_high * 1.002, 4)
                tp_ref = bands_15m.get('basis', 0)
                tp = round(tp_ref if 0 < tp_ref < current_price else (current_price - 20.0 * pip_sz), 5) if is_forex else round(tp_ref if 0 < tp_ref < current_price else (current_price * 0.985), 4)

            return {
                'triggered': True,
                'direction': dir_str,
                'rule_code': rule_code,
                'suggested_sl': sl,
                'suggested_tp': tp,
                'reason': f"🎯 REBOTE+SIPV {dir_str.upper()} ({rule_code}) validado ({macro_reason})",
                'detail': {
                    'macro_reason': macro_reason,
                    'is_sar': is_sar,
                    'sl': sl,
                    'tp': tp
                }
            }
        except Exception as e:
            log_error(MODULE, f"Error en evaluate_climax_sipv_signal para {symbol}: {e}")
            return {'triggered': False, 'direction': direction, 'reason': f"Excepción evaluando señal: {e}"}

    @classmethod
    def evaluate_position_climax(
        cls,
        pos: dict,
        current_price: float,
        memory_store: dict = None,
        candle_high: Optional[float] = None,
        candle_low: Optional[float] = None
    ) -> dict:
        """
        Evalúa si la posición toca o perfora bandas de clímax Fibonacci
        en 5m, 15m, 1h, 4h o 1d, aplicando la Propuesta B y la jerarquía de etapas.

        Returns:
            {
                'triggered': bool,
                'stage': int,            # 1 a 5
                'timeframe': str,        # '5m', '15m', etc.
                'band_name': str,        # 'lower_5', 'upper_6', etc.
                'band_price': float,
                'target_close_ratio': float, # 0.40, 0.30, 0.15, 1.00
                'action': 'PARTIAL' | 'FULL',
                'reason': str,
                'new_sl_be': float       # Precio de Break-Even sugerido
            }
        """
        result = {'triggered': False}
        if not pos or current_price <= 0:
            return result

        symbol = str(pos.get('symbol') or '').upper()
        side = (pos.get('side') or '').lower()
        is_long = side in ('long', 'buy')
        is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF', 'NZD')) or pos.get('market_type') == 'forex_futures'

        # PnL actual
        pnl_pct, pips = cls.calculate_pnl(pos, current_price)
        if pnl_pct <= 0 and pips <= 0:
            # Nunca ejecutar toma de beneficios en pérdida
            return result

        entry = float(pos.get('avg_entry_price') or pos.get('entry_price') or current_price)

        # Precio extremo de mecha (intrabar)
        eval_low = min(current_price, candle_low if candle_low is not None else current_price)
        eval_high = max(current_price, candle_high if candle_high is not None else current_price)

        current_stage = int(pos.get('climax_stage') or 0)

        # ── CÁLCULO DE BREAK-EVEN SUGERIDO ──
        if is_forex:
            pip_sz = 0.01 if ('JPY' in symbol or 'XAU' in symbol) else 0.0001
            buf = cls.BUFFER_BE_PIPS_FOREX * pip_sz
            new_sl_be = round(entry + buf if is_long else entry - buf, 5)
        else:
            buf = entry * cls.BUFFER_BE_PCT_CRYPTO
            new_sl_be = round(entry + buf if is_long else entry - buf, 4)

        # ── JERARQUÍA DE EVALUACIÓN MULTI-TEMPORALIDAD ──
        # Escaneamos de mayor a menor para priorizar etapas más avanzadas si ocurre un salto macro
        tfs = ['1d', '4h', '1h', '15m', '5m']
        bands_by_tf = {}
        for tf in tfs:
            bands = cls.get_timeframe_bands(symbol, tf, memory_store)
            if bands:
                bands_by_tf[tf] = bands

        # 1. ETAPA 5: Clímax Diario (1D Banda 5 o 6) -> Cierre Total
        if current_stage < 5 and '1d' in bands_by_tf:
            b1d = bands_by_tf['1d']
            u5, u6 = b1d.get('upper_5', 0), b1d.get('upper_6', 0)
            l5, l6 = b1d.get('lower_5', 0), b1d.get('lower_6', 0)
            hit = (eval_high >= u5 and u5 > 0) if is_long else (eval_low <= l5 and l5 > 0)
            if hit:
                band_name = 'upper_5/6_1d' if is_long else 'lower_5/6_1d'
                band_p = u5 if is_long else l5
                return {
                    'triggered': True,
                    'stage': 5,
                    'timeframe': '1d',
                    'band_name': band_name,
                    'band_price': band_p,
                    'target_close_ratio': 1.0,
                    'action': 'FULL',
                    'reason': f"Clímax Diario 1D alcanzado ({band_name} en {band_p:.4f}). Cierre total 100%.",
                    'new_sl_be': new_sl_be
                }

        # 2. ETAPA 4: Clímax Mayor (4H Banda 5/6 o 1H Banda 6) -> Cierre Total
        if current_stage < 4:
            if '4h' in bands_by_tf:
                b4h = bands_by_tf['4h']
                u5_4h, l5_4h = b4h.get('upper_5', 0), b4h.get('lower_5', 0)
                hit_4h = (eval_high >= u5_4h and u5_4h > 0) if is_long else (eval_low <= l5_4h and l5_4h > 0)
                if hit_4h:
                    band_name = 'upper_5_4h' if is_long else 'lower_5_4h'
                    band_p = u5_4h if is_long else l5_4h
                    return {
                        'triggered': True,
                        'stage': 4,
                        'timeframe': '4h',
                        'band_name': band_name,
                        'band_price': band_p,
                        'target_close_ratio': 1.0,
                        'action': 'FULL',
                        'reason': f"Clímax Mayor 4H alcanzado ({band_name} en {band_p:.4f}). Cierre total 100%.",
                        'new_sl_be': new_sl_be
                    }
            if '1h' in bands_by_tf:
                b1h = bands_by_tf['1h']
                u6_1h, l6_1h = b1h.get('upper_6', 0), b1h.get('lower_6', 0)
                hit_1h_6 = (eval_high >= u6_1h and u6_1h > 0) if is_long else (eval_low <= l6_1h and l6_1h > 0)
                if hit_1h_6:
                    band_name = 'upper_6_1h' if is_long else 'lower_6_1h'
                    band_p = u6_1h if is_long else l6_1h
                    return {
                        'triggered': True,
                        'stage': 4,
                        'timeframe': '1h',
                        'band_name': band_name,
                        'band_price': band_p,
                        'target_close_ratio': 1.0,
                        'action': 'FULL',
                        'reason': f"Extremo 1H Banda 6 alcanzado ({band_name} en {band_p:.4f}). Cierre total 100%.",
                        'new_sl_be': new_sl_be
                    }

        # 3. ETAPA 3: Clímax Intermedio (15m Banda 6 o 1H Banda 5) -> 15% Adicional
        if current_stage < 3:
            if '15m' in bands_by_tf:
                b15m = bands_by_tf['15m']
                u6_15, l6_15 = b15m.get('upper_6', 0), b15m.get('lower_6', 0)
                hit_15_6 = (eval_high >= u6_15 and u6_15 > 0) if is_long else (eval_low <= l6_15 and l6_15 > 0)
                if hit_15_6:
                    band_name = 'upper_6_15m' if is_long else 'lower_6_15m'
                    band_p = u6_15 if is_long else l6_15
                    return {
                        'triggered': True,
                        'stage': 3,
                        'timeframe': '15m',
                        'band_name': band_name,
                        'band_price': band_p,
                        'target_close_ratio': 0.15,
                        'action': 'PARTIAL',
                        'reason': f"Extremo 15m Banda 6 alcanzado ({band_name} en {band_p:.4f}). Toma parcial N3.",
                        'new_sl_be': new_sl_be
                    }
            if '1h' in bands_by_tf:
                b1h = bands_by_tf['1h']
                u5_1h, l5_1h = b1h.get('upper_5', 0), b1h.get('lower_5', 0)
                hit_1h_5 = (eval_high >= u5_1h and u5_1h > 0) if is_long else (eval_low <= l5_1h and l5_1h > 0)
                if hit_1h_5:
                    band_name = 'upper_5_1h' if is_long else 'lower_5_1h'
                    band_p = u5_1h if is_long else l5_1h
                    return {
                        'triggered': True,
                        'stage': 3,
                        'timeframe': '1h',
                        'band_name': band_name,
                        'band_price': band_p,
                        'target_close_ratio': 0.15,
                        'action': 'PARTIAL',
                        'reason': f"Agotamiento 1H Banda 5 alcanzado ({band_name} en {band_p:.4f}). Toma parcial N3.",
                        'new_sl_be': new_sl_be
                    }

        # 4. ETAPA 2: 15m Banda 5 (Propuesta B con ganancia 15m >= 0.50%) o 5m Banda 6 -> 30% Adicional
        has_min_profit_15m = (pips >= cls.MIN_PROFIT_PIPS_FOREX_15M) if is_forex else (pnl_pct >= cls.MIN_PROFIT_PCT_CRYPTO_15M)
        has_min_profit_5m  = (pips >= cls.MIN_PROFIT_PIPS_FOREX_5M) if is_forex else (pnl_pct >= cls.MIN_PROFIT_PCT_CRYPTO_5M)

        if current_stage < 2:
            # 15m Banda 5 (con Propuesta B: requiere beneficio mínimo >= +0.50% Crypto / >= +7 pips Forex)
            if '15m' in bands_by_tf and has_min_profit_15m:
                b15m = bands_by_tf['15m']
                u5_15, l5_15 = b15m.get('upper_5', 0), b15m.get('lower_5', 0)
                hit_15_5 = (eval_high >= u5_15 and u5_15 > 0) if is_long else (eval_low <= l5_15 and l5_15 > 0)
                if hit_15_5:
                    band_name = 'upper_5_15m' if is_long else 'lower_5_15m'
                    band_p = u5_15 if is_long else l5_15
                    
                    # Comprobar confluencia macro 1h/4h para Cierre 100% y Giro SAR
                    sar_dir = 'short' if is_long else 'long'
                    macro_hit, macro_reason = cls.check_macro_confluence(symbol, sar_dir, current_price, memory_store)
                    if macro_hit:
                        return {
                            'triggered': True,
                            'stage': 2,
                            'timeframe': '15m',
                            'band_name': band_name,
                            'band_price': band_p,
                            'target_close_ratio': 1.0,
                            'action': 'FULL',
                            'sar_eligible': True,
                            'sar_direction': sar_dir,
                            'reason': f"Clímax 15m Banda 5 alcanzado ({band_name} en {band_p:.4f}) con soporte/confluencia macro ({macro_reason}). Cierre total 100% y Giro SAR.",
                            'new_sl_be': new_sl_be
                        }

                    target_pct = 0.40 if current_stage == 0 else 0.30
                    return {
                        'triggered': True,
                        'stage': 2,
                        'timeframe': '15m',
                        'band_name': band_name,
                        'band_price': band_p,
                        'target_close_ratio': target_pct,
                        'action': 'PARTIAL',
                        'sar_eligible': False,
                        'reason': f"Clímax 15m Banda 5 alcanzado ({band_name} en {band_p:.4f}, PnL: +{pnl_pct:.2f}% >= +0.50%). Propuesta B 15m.",
                        'new_sl_be': new_sl_be
                    }

            # 5m Banda 6
            if '5m' in bands_by_tf:
                b5m = bands_by_tf['5m']
                u6_5m, l6_5m = b5m.get('upper_6', 0), b5m.get('lower_6', 0)
                hit_5m_6 = (eval_high >= u6_5m and u6_5m > 0) if is_long else (eval_low <= l6_5m and l6_5m > 0)
                if hit_5m_6:
                    band_name = 'upper_6_5m' if is_long else 'lower_6_5m'
                    band_p = u6_5m if is_long else l6_5m

                    sar_dir = 'short' if is_long else 'long'
                    macro_hit, macro_reason = cls.check_macro_confluence(symbol, sar_dir, current_price, memory_store)
                    if macro_hit:
                        return {
                            'triggered': True,
                            'stage': 2,
                            'timeframe': '5m',
                            'band_name': band_name,
                            'band_price': band_p,
                            'target_close_ratio': 1.0,
                            'action': 'FULL',
                            'sar_eligible': True,
                            'sar_direction': sar_dir,
                            'reason': f"Extremo 5m Banda 6 alcanzado ({band_name} en {band_p:.4f}) con soporte/confluencia macro ({macro_reason}). Cierre total 100% y Giro SAR.",
                            'new_sl_be': new_sl_be
                        }

                    target_pct = 0.40 if current_stage == 0 else 0.30
                    return {
                        'triggered': True,
                        'stage': 2,
                        'timeframe': '5m',
                        'band_name': band_name,
                        'band_price': band_p,
                        'target_close_ratio': target_pct,
                        'action': 'PARTIAL',
                        'sar_eligible': False,
                        'reason': f"Extremo 5m Banda 6 alcanzado ({band_name} en {band_p:.4f}).",
                        'new_sl_be': new_sl_be
                    }

        # 5. ETAPA 1: 5m Banda 5 (Propuesta B con ganancia mínima 5m >= 0.40%) -> 40% (o 100% si confluencia macro)
        if current_stage < 1 and '5m' in bands_by_tf:
            if has_min_profit_5m:
                b5m = bands_by_tf['5m']
                u5_5m, l5_5m = b5m.get('upper_5', 0), b5m.get('lower_5', 0)
                hit_5m_5 = (eval_high >= u5_5m and u5_5m > 0) if is_long else (eval_low <= l5_5m and l5_5m > 0)
                if hit_5m_5:
                    band_name = 'upper_5_5m' if is_long else 'lower_5_5m'
                    band_p = u5_5m if is_long else l5_5m

                    sar_dir = 'short' if is_long else 'long'
                    macro_hit, macro_reason = cls.check_macro_confluence(symbol, sar_dir, current_price, memory_store)
                    if macro_hit:
                        return {
                            'triggered': True,
                            'stage': 1,
                            'timeframe': '5m',
                            'band_name': band_name,
                            'band_price': band_p,
                            'target_close_ratio': 1.0,
                            'action': 'FULL',
                            'sar_eligible': True,
                            'sar_direction': sar_dir,
                            'reason': f"Micro-Clímax 5m Banda 5 alcanzado ({band_name} en {band_p:.4f}) con soporte/confluencia macro ({macro_reason}). Cierre total 100% y Giro SAR.",
                            'new_sl_be': new_sl_be
                        }

                    return {
                        'triggered': True,
                        'stage': 1,
                        'timeframe': '5m',
                        'band_name': band_name,
                        'band_price': band_p,
                        'target_close_ratio': 0.40,
                        'action': 'PARTIAL',
                        'sar_eligible': False,
                        'reason': f"Micro-Clímax 5m Banda 5 alcanzado ({band_name} en {band_p:.4f}, PnL: +{pnl_pct:.2f}% >= +0.40%). Propuesta B 5m.",
                        'new_sl_be': new_sl_be
                    }

        return result

    @classmethod
    def calculate_adaptive_close_size(
        cls,
        pos: dict,
        target_ratio: float,
        current_price: float,
        market_type: str = 'crypto'
    ) -> dict:
        """
        Algoritmo Adaptativo de Lote Mínimo (AdaptiveLotScale).
        Evalúa si el tamaño objetivo (ej. 40%) cumple con minQty, stepSize y minNotional.
        Si no cumple, prueba 50%/50%. Si la posición está en el mínimo indivisible,
        ejecuta CIERRE TOTAL (100%).

        Returns:
            {
                'action': 'PARTIAL' | 'FULL',
                'close_qty': float,
                'remaining_qty': float,
                'pct_closed': float,
                'ratio_type': 'target_40' | 'fallback_50' | 'indivisible_100',
                'reason': str
            }
        """
        is_forex = (market_type == 'forex' or 'forex' in str(pos.get('market_type', '')).lower())
        size_key = 'lots' if is_forex else 'size'
        total_qty = float(pos.get(size_key) or pos.get('lots') or pos.get('size') or 0.0)

        if total_qty <= 0:
            return {'action': 'REJECT', 'close_qty': 0.0, 'remaining_qty': 0.0, 'pct_closed': 0.0, 'reason': 'Tamaño de posición cero'}

        if target_ratio >= 1.0:
            return {
                'action': 'FULL',
                'close_qty': total_qty,
                'remaining_qty': 0.0,
                'pct_closed': 100.0,
                'ratio_type': 'target_100',
                'reason': 'Cierre total solicitado por Etapa Macro'
            }

        if is_forex:
            # ── REGLAS DE FOREX (cTrader / IC Markets) ──
            min_lots = 0.01
            lot_step = 0.01

            # Intento 1: target_ratio (ej 0.40)
            close_1 = round(math.floor(total_qty * target_ratio / lot_step) * lot_step, 2)
            rem_1 = round(total_qty - close_1, 2)

            if close_1 >= min_lots and rem_1 >= min_lots:
                return {
                    'action': 'PARTIAL',
                    'close_qty': close_1,
                    'remaining_qty': rem_1,
                    'pct_closed': round(close_1 / total_qty * 100, 1),
                    'ratio_type': 'target_adaptive',
                    'reason': f"Parcial {target_ratio*100:.0f}% aprobado ({close_1} lotes, remanente {rem_1})"
                }

            # Intento 2: 50% / 50%
            close_2 = round(math.floor(total_qty * 0.50 / lot_step) * lot_step, 2)
            rem_2 = round(total_qty - close_2, 2)

            if close_2 >= min_lots and rem_2 >= min_lots:
                return {
                    'action': 'PARTIAL',
                    'close_qty': close_2,
                    'remaining_qty': rem_2,
                    'pct_closed': round(close_2 / total_qty * 100, 1),
                    'ratio_type': 'fallback_50',
                    'reason': f"Ajustado a 50% por tamaño mínimo ({close_2} lotes, remanente {rem_2})"
                }

            # Intento 3: Posición indivisible (0.01 lotes) -> Full Close 100%
            return {
                'action': 'FULL',
                'close_qty': total_qty,
                'remaining_qty': 0.0,
                'pct_closed': 100.0,
                'ratio_type': 'indivisible_100',
                'reason': f"Posición indivisible en lote mínimo ({total_qty} lotes). Cierre total 100%."
            }

        else:
            # ── REGLAS DE CRYPTO FUTURES (Binance) ──
            symbol = str(pos.get('symbol') or '').replace('/', '').upper()
            step_size = 0.001
            min_qty = 0.001
            min_notional = 5.0  # Típicamente $5 USD mínimo en Binance Futures

            # Intentar obtener info precisa de Binance si está disponible en cache
            try:
                from app.execution.binance_connector import get_client, get_futures_symbol_info_cached
                client = get_client()
                info = get_futures_symbol_info_cached(client, symbol)
                if info:
                    step_size = float(info.get('step_size') or step_size)
                    min_qty = float(info.get('min_qty') or min_qty)
                    min_notional = float(info.get('min_notional') or min_notional)
            except Exception:
                pass  # Fallback a defaults seguros

            def round_step(val, step):
                precision = max(0, int(round(-math.log10(step))))
                return round(math.floor(val / step) * step, precision)

            # Intento 1: target_ratio (ej 0.40)
            close_1 = round_step(total_qty * target_ratio, step_size)
            rem_1 = round_step(total_qty - close_1, step_size)
            notional_close_1 = close_1 * current_price
            notional_rem_1 = rem_1 * current_price

            if (close_1 >= min_qty and rem_1 >= min_qty and
                notional_close_1 >= min_notional and notional_rem_1 >= min_notional):
                return {
                    'action': 'PARTIAL',
                    'close_qty': close_1,
                    'remaining_qty': rem_1,
                    'pct_closed': round(close_1 / total_qty * 100, 1),
                    'ratio_type': 'target_adaptive',
                    'reason': f"Parcial {target_ratio*100:.0f}% aprobado ({close_1} {symbol}, ${notional_close_1:.2f})"
                }

            # Intento 2: 50% / 50%
            close_2 = round_step(total_qty * 0.50, step_size)
            rem_2 = round_step(total_qty - close_2, step_size)
            notional_close_2 = close_2 * current_price
            notional_rem_2 = rem_2 * current_price

            if (close_2 >= min_qty and rem_2 >= min_qty and
                notional_close_2 >= min_notional and notional_rem_2 >= min_notional):
                return {
                    'action': 'PARTIAL',
                    'close_qty': close_2,
                    'remaining_qty': rem_2,
                    'pct_closed': round(close_2 / total_qty * 100, 1),
                    'ratio_type': 'fallback_50',
                    'reason': f"Ajustado a 50% por límites de Binance ({close_2} {symbol}, ${notional_close_2:.2f})"
                }

            # Intento 3: Posición Indivisible -> Full Close 100%
            return {
                'action': 'FULL',
                'close_qty': total_qty,
                'remaining_qty': 0.0,
                'pct_closed': 100.0,
                'ratio_type': 'indivisible_100',
                'reason': f"Posición indivisible en límite de Binance ({total_qty} {symbol}, ${total_qty*current_price:.2f}). Cierre total 100%."
            }
