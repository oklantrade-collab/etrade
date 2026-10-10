"""
ADUANAS Multi-TF Fibonacci Climax Manager — Cierre Parcial Adaptativo y Blindaje Break-Even
Mercados: Crypto Futures (Binance) & Forex (IC Markets / cTrader)
Temporalidades: 5m, 15m, 1h, 4h, 1d
"""

import math
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
                    # Si no había ejecutado Etapa 1, tomar 40% inicial de Etapa 1
                    target_pct = 0.40 if current_stage == 0 else 0.30
                    return {
                        'triggered': True,
                        'stage': 2,
                        'timeframe': '15m',
                        'band_name': band_name,
                        'band_price': band_p,
                        'target_close_ratio': target_pct,
                        'action': 'PARTIAL',
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
                    target_pct = 0.40 if current_stage == 0 else 0.30
                    return {
                        'triggered': True,
                        'stage': 2,
                        'timeframe': '5m',
                        'band_name': band_name,
                        'band_price': band_p,
                        'target_close_ratio': target_pct,
                        'action': 'PARTIAL',
                        'reason': f"Extremo 5m Banda 6 alcanzado ({band_name} en {band_p:.4f}).",
                        'new_sl_be': new_sl_be
                    }

        # 5. ETAPA 1: 5m Banda 5 (Propuesta B con ganancia mínima 5m >= 0.40%) -> 40%
        if current_stage < 1 and '5m' in bands_by_tf:
            if has_min_profit_5m:
                b5m = bands_by_tf['5m']
                u5_5m, l5_5m = b5m.get('upper_5', 0), b5m.get('lower_5', 0)
                hit_5m_5 = (eval_high >= u5_5m and u5_5m > 0) if is_long else (eval_low <= l5_5m and l5_5m > 0)
                if hit_5m_5:
                    band_name = 'upper_5_5m' if is_long else 'lower_5_5m'
                    band_p = u5_5m if is_long else l5_5m
                    return {
                        'triggered': True,
                        'stage': 1,
                        'timeframe': '5m',
                        'band_name': band_name,
                        'band_price': band_p,
                        'target_close_ratio': 0.40,
                        'action': 'PARTIAL',
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
