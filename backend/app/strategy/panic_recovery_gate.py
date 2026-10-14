"""
eTrade v5.0 / v6.0 — PANIC RECOVERY GATE & MACRO EXTREME GATEKEEPER
=====================================================================
Motor Unificado de Pánico, Rescate EREP, Inmunidad en Zonas Extremas de Fibonacci
y Escalamiento Macro (1H, 4H, 1D) para Crypto y Forex (LONG y SHORT).

Pilares Operativos:
1. Blindaje de Stop Loss: Prohibido stop_loss = 0.
2. Inmunidad en Zonas Extremas (15m): Si el precio oscila en UPPER_5/6 o LOWER_5/6,
   se suspende el corte del 5% y EREP busca el P2 para salir en P3 Breakeven ($0.00 o < $1.00).
3. Stop por Ruptura Estructural: Se corta si una vela de 15m cierra con cuerpo entero
   más allá de la banda extrema (+ buffer de 0.8% / 1.5 ATR).
4. Macro Extreme Gatekeeper (1H, 4H, 1D): Orden MARKET confirmada por mecha SIPV/desaceleración
   en UPPER_6 (SHORT) o LOWER_6 (LONG) para nueva entrada o refuerzo P2 con cálculo de P3 Breakeven.
5. Modo Pánico Regular en Zonas Intermedias: Salida en micro-breakeven al primer micro-giro,
   corte por expansión de Bollinger o cruce EMA3xEMA9 en contra, o Hard Cap del 5%.
"""

import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.core.logger import log_info, log_warning, log_error

MODULE = "PANIC_RECOVERY_GATE"


def calculate_fibonacci_bands(df: pd.DataFrame, current_price: float) -> dict:
    """
    Calcula los niveles de Fibonacci Bollinger (1..6) para cualquier timeframe.
    """
    if df is None or len(df) < 15:
        return {
            "basis": current_price,
            "upper_band": current_price * 1.01,
            "lower_band": current_price * 0.99,
            "upper_5": current_price * 1.02,
            "upper_6": current_price * 1.03,
            "lower_5": current_price * 0.98,
            "lower_6": current_price * 0.97,
            "atr": current_price * 0.005,
            "bandwidth": 0.02
        }

    try:
        df_c = df.copy()
        df_c.columns = [str(col).lower() for col in df_c.columns]
        c = df_c['close']
        last = df_c.iloc[-1]
        
        basis = float(last.get('basis') or c.rolling(20, min_periods=1).mean().iloc[-1])
        std = float(c.rolling(20, min_periods=1).std().iloc[-1])
        if std == 0 or math.isnan(std):
            std = current_price * 0.002

        if 'tr' not in df_c.columns:
            high = df_c['high'] if 'high' in df_c.columns else c
            low = df_c['low'] if 'low' in df_c.columns else c
            prev_close = c.shift(1).fillna(c)
            tr = np.maximum(high - low, np.maximum(abs(high - prev_close), abs(low - prev_close)))
            df_c['tr'] = tr
        atr = float(df_c['tr'].rolling(14, min_periods=1).mean().iloc[-1])
        if atr <= 0 or math.isnan(atr):
            atr = current_price * 0.002

        upper_band = basis + (2.0 * std)
        lower_band = basis - (2.0 * std)
        bandwidth = (upper_band - lower_band) / basis if basis > 0 else 0.02

        upper_1 = basis + (0.236 * 3.0 * std)
        upper_2 = basis + (0.382 * 3.0 * std)
        upper_3 = basis + (0.500 * 3.0 * std)
        upper_4 = basis + (0.618 * 3.0 * std)
        upper_5 = basis + (5.618 * atr)
        upper_6 = basis + (6.618 * atr)

        lower_1 = basis - (0.236 * 3.0 * std)
        lower_2 = basis - (0.382 * 3.0 * std)
        lower_3 = basis - (0.500 * 3.0 * std)
        lower_4 = basis - (0.618 * 3.0 * std)
        lower_5 = basis - (5.618 * atr)
        lower_6 = basis - (6.618 * atr)

        return {
            "basis": basis,
            "upper_band": upper_band,
            "lower_band": lower_band,
            "bandwidth": bandwidth,
            "upper_1": upper_1,
            "upper_2": upper_2,
            "upper_3": upper_3,
            "upper_4": upper_4,
            "upper_5": upper_5,
            "upper_6": upper_6,
            "lower_1": lower_1,
            "lower_2": lower_2,
            "lower_3": lower_3,
            "lower_4": lower_4,
            "lower_5": lower_5,
            "lower_6": lower_6,
            "atr": atr
        }
    except Exception as e:
        log_error(MODULE, f"Error calculando bandas de Fibonacci: {e}")
        return {
            "basis": current_price,
            "upper_band": current_price * 1.01,
            "lower_band": current_price * 0.99,
            "upper_5": current_price * 1.02,
            "upper_6": current_price * 1.03,
            "lower_5": current_price * 0.98,
            "lower_6": current_price * 0.97,
            "atr": current_price * 0.005,
            "bandwidth": 0.02
        }


def check_candle_rejection(df: pd.DataFrame, side_expected: str) -> dict:
    """
    Verifica si la vela más reciente o la anterior presenta mecha de rechazo
    o desaceleración de volumen institucional (SIPV).
    
    Para SHORT (buscando caída): mecha superior >= 25% del rango total de la vela.
    Para LONG (buscando rebote): mecha inferior >= 25% del rango total de la vela.
    """
    if df is None or len(df) < 1:
        return {'confirmed': False, 'wick_ratio': 0.0, 'reason': 'Insuficientes velas para evaluar mecha'}

    try:
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        def get_wick_ratio(row, side):
            o = float(row.get('open', 0))
            c = float(row.get('close', 0))
            h = float(row.get('high', 0))
            l = float(row.get('low', 0))
            rng = max(1e-9, h - l)
            if side in ('short', 'sell'):
                upper_body = max(o, c)
                upper_wick = h - upper_body
                return upper_wick / rng
            else:
                lower_body = min(o, c)
                lower_wick = lower_body - l
                return lower_wick / rng

        w_last = get_wick_ratio(last, side_expected)
        w_prev = get_wick_ratio(prev, side_expected)
        best_wick = max(w_last, w_prev)

        # Confirmación de mecha >= 25%
        if best_wick >= 0.25:
            return {
                'confirmed': True,
                'wick_ratio': round(best_wick, 3),
                'reason': f"Mecha de rechazo confirmada ({best_wick*100:.1f}% >= 25%) para {side_expected.upper()}"
            }

        # Verificación alternativa: Giro de EMA3 en la vela más reciente
        if len(df) >= 3 and 'close' in df.columns:
            ema3 = df['close'].ewm(span=3, adjust=False).mean()
            if side_expected in ('short', 'sell') and ema3.iloc[-1] < ema3.iloc[-2]:
                return {
                    'confirmed': True,
                    'wick_ratio': round(best_wick, 3),
                    'reason': f"Desaceleración EMA3 descendente confirmada para SHORT"
                }
            elif side_expected in ('long', 'buy') and ema3.iloc[-1] > ema3.iloc[-2]:
                return {
                    'confirmed': True,
                    'wick_ratio': round(best_wick, 3),
                    'reason': f"Desaceleración EMA3 ascendente confirmada para LONG"
                }

        return {
            'confirmed': False,
            'wick_ratio': round(best_wick, 3),
            'reason': f"Mecha insuficiente ({best_wick*100:.1f}% < 25%) y sin giro EMA3"
        }
    except Exception as e:
        log_error(MODULE, f"Error evaluando mecha de rechazo: {e}")
        return {'confirmed': False, 'wick_ratio': 0.0, 'reason': f"Error: {e}"}


def evaluate_panic_and_erep_status(
    position: dict,
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    df_4h: Optional[pd.DataFrame] = None,
    snap: Optional[dict] = None,
    df_1d: Optional[pd.DataFrame] = None
) -> dict:
    """
    Evalúa el estado de Pánico, Rescate EREP, Inmunidad en Zonas Extremas y Salidas Defensivas.
    Soporta Crypto y Forex, LONG y SHORT.
    Incluye Escudo Macro 1D para evitar cierres prematuros en retrocesos de tendencia favorable.
    """
    if not position or current_price <= 0:
        return {'should_exit': False, 'action': 'NONE', 'immunity_active': False, 'reason': 'Sin posición o precio'}

    side = (position.get('side') or '').lower()
    is_long = side in ('long', 'buy')
    symbol = position.get('symbol', '')
    is_forex = any(x in symbol for x in ('EUR', 'GBP', 'JPY', 'XAU', 'AUD', 'CAD', 'CHF')) or position.get('market_type') == 'forex_futures'

    # 1. Obtener precios de entrada y cálculo de PnL
    entry = float(position.get('erep_p3_avg') or position.get('avg_entry_price') or position.get('avg_price') or position.get('entry_price') or 0.0)
    if entry <= 0:
        return {'should_exit': False, 'action': 'NONE', 'immunity_active': False, 'reason': 'Entry price inválido'}

    # Tamaño y cálculo de capital/inversión
    qty = float(position.get('size') or position.get('lots') or position.get('shares') or position.get('quantity') or 0.0)
    capital_invested = float(position.get('total_investment') or position.get('total_cost') or 0.0)
    
    # Estimación de capital invertido si no vino precalculado
    if capital_invested <= 0:
        if is_forex:
            lev = 100.0
            mult = 100.0 if 'XAU' in symbol else 100000.0
            capital_invested = (abs(qty) * mult * (current_price if not symbol.startswith('USD') else 1.0)) / lev
        else:
            lev = float(position.get('leverage') or 5.0)
            capital_invested = (abs(qty) * entry) / max(1.0, lev)
    capital_invested = max(5.0, capital_invested)

    # PnL en porcentaje y USD
    if is_long:
        pnl_pct = (current_price - entry) / entry * 100.0
    else:
        pnl_pct = (entry - current_price) / entry * 100.0

    pnl_usd = float(position.get('unrealized_pnl') or position.get('pnl_usd') or 0.0)
    if pnl_usd == 0 and capital_invested > 0:
        lev = float(position.get('leverage') or (100.0 if is_forex else 5.0))
        pnl_usd = capital_invested * lev * (pnl_pct / 100.0)

    # 2. Bandas de Fibonacci en 15m
    # Usar velas cerradas previas como referencia si hay al menos 2 velas,
    # para evitar que una vela de ruptura en curso infle artificialmente el umbral de las bandas.
    df_ref_15m = df_15m.iloc[:-1] if (df_15m is not None and len(df_15m) >= 2) else df_15m
    fib_15m = calculate_fibonacci_bands(df_ref_15m, current_price)
    u5 = fib_15m['upper_5']
    u6 = fib_15m['upper_6']
    l5 = fib_15m['lower_5']
    l6 = fib_15m['lower_6']
    atr_15m = fib_15m['atr']

    # Identificar si está en Zona Extrema de Fibonacci (15m o 1H)
    buf_atr = atr_15m * 0.3
    in_extreme_zone = False
    if not is_long:
        in_extreme_zone = (current_price >= (u5 - buf_atr))
    else:
        in_extreme_zone = (current_price <= (l5 + buf_atr))

    # Soporte/Resistencia Extrema en Banda Bollinger 1H
    if df_1h is not None and len(df_1h) >= 20:
        c1h = df_1h['close'] if 'close' in df_1h.columns else df_1h.get('c', pd.Series())
        mean_1h = float(c1h.rolling(20).mean().iloc[-1])
        std_1h = float(c1h.rolling(20).std().iloc[-1])
        bb_upper_1h = mean_1h + 2.0 * std_1h
        bb_lower_1h = mean_1h - 2.0 * std_1h
        buf_1h = std_1h * 0.20
        if is_long and current_price <= (bb_lower_1h + buf_1h):
            in_extreme_zone = True
        elif not is_long and current_price >= (bb_upper_1h - buf_1h):
            in_extreme_zone = True

    # ── ESCUDO MACRO (Tendencia Diaria 1D o Estructural 4H) ──
    macro_1d_aligned = False
    macro_1d_detail = ""
    if df_1d is not None and len(df_1d) >= 2:
        c1d = df_1d['close'] if 'close' in df_1d.columns else df_1d.get('c', pd.Series())
        if len(c1d) >= 2:
            ema3_1d_curr = float(c1d.ewm(span=3, adjust=False).mean().iloc[-1])
            ema3_1d_prev = float(c1d.ewm(span=3, adjust=False).mean().iloc[-2])
            ema9_1d_curr = float(c1d.ewm(span=9, adjust=False).mean().iloc[-1])
            if is_long:
                if (ema3_1d_curr >= ema9_1d_curr) or (ema3_1d_curr >= ema3_1d_prev):
                    macro_1d_aligned = True
                    macro_1d_detail = f"1D Alcista (EMA3={ema3_1d_curr:.4f} vs prev={ema3_1d_prev:.4f}, EMA9={ema9_1d_curr:.4f})"
            else:
                if (ema3_1d_curr <= ema9_1d_curr) or (ema3_1d_curr <= ema3_1d_prev):
                    macro_1d_aligned = True
                    macro_1d_detail = f"1D Bajista (EMA3={ema3_1d_curr:.4f} vs prev={ema3_1d_prev:.4f}, EMA9={ema9_1d_curr:.4f})"
    elif snap:
        trend_1d = str(snap.get('trend_1d') or snap.get('regime_1d') or '').lower()
        ema3_1d = float(snap.get('ema3_1d') or snap.get('ema_3_1d') or 0.0)
        ema9_1d = float(snap.get('ema9_1d') or snap.get('ema_9_1d') or 0.0)
        if is_long and ('bull' in trend_1d or (ema3_1d > 0 and ema3_1d >= ema9_1d)):
            macro_1d_aligned = True
            macro_1d_detail = f"1D Alcista (Snapshot={trend_1d})"
        elif not is_long and ('bear' in trend_1d or (ema3_1d > 0 and ema3_1d <= ema9_1d)):
            macro_1d_aligned = True
            macro_1d_detail = f"1D Bajista (Snapshot={trend_1d})"

    macro_4h_aligned = False
    macro_4h_detail = ""
    if df_4h is not None and len(df_4h) >= 2:
        c4h = df_4h['close'] if 'close' in df_4h.columns else df_4h.get('c', pd.Series())
        if len(c4h) >= 2:
            ema3_4h_curr = float(c4h.ewm(span=3, adjust=False).mean().iloc[-1])
            ema3_4h_prev = float(c4h.ewm(span=3, adjust=False).mean().iloc[-2])
            ema9_4h_curr = float(c4h.ewm(span=9, adjust=False).mean().iloc[-1])
            ema20_4h_curr = float(c4h.ewm(span=20, adjust=False).mean().iloc[-1]) if len(c4h) >= 20 else ema9_4h_curr
            c4h_last = float(c4h.iloc[-1])
            if is_long:
                if (ema3_4h_curr >= ema9_4h_curr) or (ema3_4h_curr >= ema3_4h_prev) or (c4h_last >= ema20_4h_curr):
                    macro_4h_aligned = True
                    macro_4h_detail = f"4H Alcista (EMA3={ema3_4h_curr:.4f} vs prev={ema3_4h_prev:.4f}, EMA9={ema9_4h_curr:.4f})"
            else:
                if (ema3_4h_curr <= ema9_4h_curr) or (ema3_4h_curr <= ema3_4h_prev) or (c4h_last <= ema20_4h_curr):
                    macro_4h_aligned = True
                    macro_4h_detail = f"4H Bajista (EMA3={ema3_4h_curr:.4f} vs prev={ema3_4h_prev:.4f}, EMA9={ema9_4h_curr:.4f})"
    elif snap:
        trend_4h = str(snap.get('trend_4h') or snap.get('regime_4h') or snap.get('mtf_4h_trend') or '').lower()
        sar_4h_val = int(snap.get('sar_trend_4h', 0))
        ema3_4h = float(snap.get('ema3_4h') or snap.get('ema_3_4h') or 0.0)
        ema9_4h = float(snap.get('ema9_4h') or snap.get('ema_9_4h') or 0.0)
        if is_long and ('bull' in trend_4h or 'long' in trend_4h or sar_4h_val >= 0 or (ema3_4h > 0 and ema3_4h >= ema9_4h)):
            macro_4h_aligned = True
            macro_4h_detail = f"4H Alcista (Snapshot={trend_4h or f'SAR={sar_4h_val}'})"
        elif not is_long and ('bear' in trend_4h or 'short' in trend_4h or sar_4h_val <= 0 or (ema3_4h > 0 and ema3_4h <= ema9_4h)):
            macro_4h_aligned = True
            macro_4h_detail = f"4H Bajista (Snapshot={trend_4h or f'SAR={sar_4h_val}'})"

    # Confluencia: 1D "o" 4H respaldan la posición
    macro_shield_active = macro_1d_aligned or macro_4h_aligned
    macro_details = []
    if macro_1d_aligned:
        macro_details.append(macro_1d_detail)
    if macro_4h_aligned:
        macro_details.append(macro_4h_detail)
    macro_trend_detail = " | ".join(macro_details) if macro_details else "Sin respaldo macro"

    if macro_1d_aligned and not macro_4h_aligned:
        macro_shield_rule_code = 'MACRO_1D_SHIELD_ACTIVE'
    elif macro_4h_aligned and not macro_1d_aligned:
        macro_shield_rule_code = 'MACRO_4H_SHIELD_ACTIVE'
    else:
        macro_shield_rule_code = 'MACRO_CONFLUENCE_SHIELD_ACTIVE' if macro_shield_active else 'NO_SHIELD'

    # Compatibilidad interna
    macro_1d_aligned = macro_shield_active

    # ── CASO A: SI LA POSICIÓN ESTÁ EN GANANCIA (PnL > 0) ──
    if pnl_usd >= 0:
        return {
            'should_exit': False,
            'action': 'NONE',
            'in_extreme_zone': in_extreme_zone,
            'immunity_active': False,
            'reason': f"Posición en ganancia (+${pnl_usd:.2f}, +{pnl_pct:.2f}%). Flujo regular."
        }

    # ── CASO B: DETECCIÓN DE ENTRADA A MODO PÁNICO / RESCATE ──
    is_erep_handling = bool(position.get('erep_active')) or (int(position.get('erep_phase', 0)) > 0)
    has_prior_panic = bool(position.get('panic_active'))
    is_in_panic = (pnl_usd <= -0.80) or (pnl_pct <= -0.80) or has_prior_panic
    
    # Si EREP está gestionando activamente la posición, no interferir con MICRO_BREAKEVEN_EXIT
    if is_erep_handling and not in_extreme_zone:
        return {
            'should_exit': False,
            'action': 'NONE',
            'in_extreme_zone': False,
            'immunity_active': False,
            'reason': f"Posición bajo gestión activa EREP (Fase {position.get('erep_phase', 1)}). Prioridad al motor EREP."
        }

    if not is_in_panic and not in_extreme_zone:
        return {
            'should_exit': False,
            'action': 'NONE',
            'in_extreme_zone': False,
            'immunity_active': False,
            'reason': f"Drawdown menor (${pnl_usd:.2f}). Fuera de umbral de pánico."
        }

    # ── PILAR 2: MICRO-BREAKEVEN TARGET ($0.00 o pérdida <= -$0.50 USD) ──
    # Si la posición en rescate recupera hacia breakeven en un retroceso: SALIR URGENTE
    if not is_erep_handling and has_prior_panic and (pnl_usd >= -0.50 or pnl_pct >= -0.30):
        return {
            'should_exit': True,
            'action': 'MICRO_BREAKEVEN_EXIT',
            'in_extreme_zone': in_extreme_zone,
            'immunity_active': False,
            'rule_code': 'PANIC_MICRO_BREAKEVEN_EXIT',
            'reason': f"Objetivo de Pánico alcanzado: PnL recuperó a ${pnl_usd:.2f} (Breakeven/mínima pérdida). Cerrando a mercado urgente."
        }

    # ── PILAR 2 & 4: EVALUACIÓN SEGÚN ZONA (EXTREMA vs INTERMEDIA) ──
    if in_extreme_zone:
        # ── ZONA EXTREMA (UPPER_5/6 para SHORT o LOWER_5/6 para LONG): INMUNIDAD ACTIVA ──
        breakout_buffer = atr_15m * 1.5
        structural_breakout = False
        breakout_detail = ""

        if df_15m is not None and len(df_15m) >= 1:
            last_candle = df_15m.iloc[-1]
            close_15m = float(last_candle.get('close', current_price))

            if not is_long:
                if (current_price > (u6 + breakout_buffer) or close_15m > (u6 + breakout_buffer)):
                    structural_breakout = True
                    breakout_detail = f"Precio actual (${current_price:.4f}) / Cierre (${close_15m:.4f}) perforó techo UPPER_6 (${u6:.4f} + {breakout_buffer:.4f})"
            else:
                if (current_price < (l6 - breakout_buffer) or close_15m < (l6 - breakout_buffer)):
                    structural_breakout = True
                    breakout_detail = f"Precio actual (${current_price:.4f}) / Cierre (${close_15m:.4f}) perforó suelo LOWER_6 (${l6:.4f} - {breakout_buffer:.4f})"

        if structural_breakout:
            return {
                'should_exit': True,
                'action': 'STRUCTURAL_BREAKOUT_EXIT',
                'in_extreme_zone': True,
                'immunity_active': False,
                'rule_code': 'STRUCTURAL_BREAKOUT_CUT',
                'reason': f"Corte por Ruptura Estructural de Banda Extrema: {breakout_detail}. Cerrando para evitar rally infinito."
            }

        # Inmunidad activa: EREP tiene el control, mantener posición y calcular SL estructural
        suggested_sl = (u6 + breakout_buffer) if not is_long else (l6 - breakout_buffer)
        return {
            'should_exit': False,
            'action': 'WAIT_EREP_RECOVERY',
            'in_extreme_zone': True,
            'immunity_active': True,
            'suggested_sl': round(suggested_sl, 5),
            'reason': f"Inmunidad Activa en Zona Extrema (UPPER_5/6 o LOWER_5/6). Hard Cap 5% suspendido. EREP gestiona P2 hacia Breakeven P3."
        }

    else:
        # ── ZONA INTERMEDIA (Zonas 1 a 4): MODO PÁNICO REGULAR ──
        # 1. Corte si la pérdida alcanza el límite tolerable de pánico (8% para stocks, 5% para crypto/forex o configurado)
        loss_pct_of_capital = abs(pnl_usd) / capital_invested * 100.0
        is_stocks = position.get('market_type') == 'stocks_spot' or position.get('shares') is not None
        default_limit = 8.0 if is_stocks else 5.0
        panic_limit = float(position.get('erep_max_loss_pct') or position.get('sl_wait_threshold') or default_limit)
        if loss_pct_of_capital >= panic_limit or pnl_pct <= -panic_limit:
            action_code = 'HARD_CAP_5PCT_EXIT' if panic_limit == 5.0 else 'HARD_CAP_PANIC_EXIT'
            return {
                'should_exit': True,
                'action': action_code,
                'in_extreme_zone': False,
                'immunity_active': False,
                'rule_code': 'PANIC_HARD_CAP_5PCT' if action_code == 'HARD_CAP_5PCT_EXIT' else 'PANIC_HARD_CAP_CUT',
                'reason': f"Hard Cap de Inversión alcanzado: Pérdida ${abs(pnl_usd):.2f} representa {loss_pct_of_capital:.1f}% del capital (>= {panic_limit:.1f}%). Corte incondicional.",
            }

        # 2. Corte por Apertura Explosiva de Bandas de Bollinger en 15m en contra
        if df_15m is not None and len(df_15m) >= 20 and not macro_1d_aligned:
            bw = fib_15m['bandwidth']
            # Si el bandwidth se expandió > 35% y el precio cabalga la banda opuesta
            if not is_long and current_price >= fib_15m['upper_band']:
                return {
                    'should_exit': True,
                    'action': 'BOLLINGER_EXPANSION_ESCAPE',
                    'in_extreme_zone': False,
                    'immunity_active': False,
                    'rule_code': 'BOLLINGER_EXPANSION_CUT',
                    'reason': f"Escape por Ruptura de Volatilidad: Bandas 15m expandiéndose con precio superando banda superior (${fib_15m['upper_band']:.4f})."
                }
            elif is_long and current_price <= fib_15m['lower_band']:
                return {
                    'should_exit': True,
                    'action': 'BOLLINGER_EXPANSION_ESCAPE',
                    'in_extreme_zone': False,
                    'immunity_active': False,
                    'rule_code': 'BOLLINGER_EXPANSION_CUT',
                    'reason': f"Escape por Ruptura de Volatilidad: Bandas 15m expandiéndose con precio perforando banda inferior (${fib_15m['lower_band']:.4f})."
                }

        # 3. Corte por EMA3 x EMA9 alineadas en contra en 15m y 1h
        if df_15m is not None and len(df_15m) >= 10 and df_1h is not None and len(df_1h) >= 10:
            c15 = df_15m['close']
            c1h = df_1h['close']
            ema3_15m = float(c15.ewm(span=3, adjust=False).mean().iloc[-1])
            ema9_15m = float(c15.ewm(span=9, adjust=False).mean().iloc[-1])
            ema3_1h = float(c1h.ewm(span=3, adjust=False).mean().iloc[-1])
            ema9_1h = float(c1h.ewm(span=9, adjust=False).mean().iloc[-1])

            if not is_long and (ema3_15m > ema9_15m) and (ema3_1h > ema9_1h):
                if macro_1d_aligned:
                    return {
                        'should_exit': False,
                        'action': 'WAIT_MACRO_RECOVERY',
                        'in_extreme_zone': in_extreme_zone,
                        'immunity_active': True,
                        'route_to_erep_1h': True,
                        'rule_code': macro_shield_rule_code,
                        'reason': f"Escape MTF suspendido por Escudo Macro 1D/4H: {macro_trend_detail}. Se mantiene SHORT para absorción/rescate EREP en resistencias 1H."
                    }
                return {
                    'should_exit': True,
                    'action': 'EMA_MTF_REVERSAL_ESCAPE',
                    'in_extreme_zone': False,
                    'immunity_active': False,
                    'rule_code': 'EMA_MTF_REVERSAL_CUT',
                    'reason': f"Escape por Momentum MTF en contra: EMA3 > EMA9 tanto en 15m como en 1h para posición SHORT sin respaldo Macro 1D o 4H."
                }
            elif is_long and (ema3_15m < ema9_15m) and (ema3_1h < ema9_1h):
                if macro_1d_aligned:
                    return {
                        'should_exit': False,
                        'action': 'WAIT_MACRO_RECOVERY',
                        'in_extreme_zone': in_extreme_zone,
                        'immunity_active': True,
                        'route_to_erep_1h': True,
                        'rule_code': macro_shield_rule_code,
                        'reason': f"Escape MTF suspendido por Escudo Macro 1D/4H: {macro_trend_detail}. Se mantiene LONG para absorción/rescate EREP en soportes 1H."
                    }
                return {
                    'should_exit': True,
                    'action': 'EMA_MTF_REVERSAL_ESCAPE',
                    'in_extreme_zone': False,
                    'immunity_active': False,
                    'rule_code': 'EMA_MTF_REVERSAL_CUT',
                    'reason': f"Escape por Momentum MTF en contra: EMA3 < EMA9 tanto en 15m como en 1h para posición LONG sin respaldo Macro 1D o 4H."
                }

        # Si aún no toca corte, permanece en pánico buscando micro-breakeven
        return {
            'should_exit': False,
            'action': 'NONE',
            'in_extreme_zone': False,
            'immunity_active': False,
            'reason': f"Modo Pánico activo en zona intermedia. Buscando micro-breakeven en micro-giro 5m."
        }


def evaluate_macro_extreme_entry(
    symbol: str,
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    df_4h: Optional[pd.DataFrame] = None,
    df_1d: Optional[pd.DataFrame] = None,
    open_positions_for_symbol: Optional[List[dict]] = None
) -> dict:
    """
    Macro Extreme Gatekeeper (1H, 4H, 1D).
    Evalúa si el precio está interactuando con UPPER_6 o LOWER_6 en temporalidades macro.
    Si se confirma con mecha SIPV/desaceleración:
      - Si NO hay posición: recomienda apertura MARKET inmediata (Clímax Macro A+).
      - Si YA HAY posición: recomienda P2 Macro para arrastrar el precio a P3 Breakeven.
    """
    if current_price <= 0:
        return {'trigger': False, 'reason': 'Precio inválido'}

    # Evaluar bandas en 1H, 4H y 1D
    macro_frames = {'1h': df_1h, '4h': df_4h, '1d': df_1d}
    hit_tf = None
    side_suggested = None
    level_touched = None
    level_price = 0.0

    for tf_name, tf_df in macro_frames.items():
        if tf_df is None or len(tf_df) < 15:
            continue
        ref_px = float(tf_df['close'].iloc[-1])
        bands = calculate_fibonacci_bands(tf_df, ref_px)
        u6 = bands['upper_6']
        l6 = bands['lower_6']
        atr = bands['atr']
        buffer = atr * 0.5

        # Chequeo UPPER_6 (SHORT)
        if current_price >= (u6 - buffer):
            hit_tf = tf_name
            side_suggested = 'short'
            level_touched = 'UPPER_6'
            level_price = u6
            break
        # Chequeo LOWER_6 (LONG)
        elif current_price <= (l6 + buffer):
            hit_tf = tf_name
            side_suggested = 'long'
            level_touched = 'LOWER_6'
            level_price = l6
            break

    if not hit_tf:
        return {'trigger': False, 'reason': 'Precio fuera de bandas macro UPPER_6 / LOWER_6'}

    # Confirmación de mecha en 5m o 15m
    rejection_5m = check_candle_rejection(df_5m, side_suggested)
    rejection_15m = check_candle_rejection(df_15m, side_suggested)
    confirmed = rejection_5m['confirmed'] or rejection_15m['confirmed']

    if not confirmed:
        return {
            'trigger': False,
            'reason': f"Precio en {level_touched} macro ({hit_tf.upper()}), pero sin mecha de rechazo aún en 5m/15m."
        }

    # Evaluar si ya existe posición abierta para este símbolo
    open_pos = (open_positions_for_symbol or [])
    active_same_side = [p for p in open_pos if (p.get('side') or '').lower() == side_suggested]

    if not active_same_side:
        # Caso A: Entrada Maestra A+ nueva
        return {
            'trigger': True,
            'action': 'ENTER_MACRO_CLIMAX',
            'order_type': 'MARKET',
            'side': side_suggested,
            'timeframe': hit_tf,
            'level': level_touched,
            'level_price': level_price,
            'rule_code': f"MACRO_CLIMAX_{hit_tf.upper()}_{level_touched}",
            'score_bonus': 30,
            'reason': f"Clímax Macro A+ en {hit_tf.upper()} ({level_touched} @ {level_price:.4f}) con mecha confirmada. Ejecución MARKET inmediata."
        }
    else:
        # Caso B: Ya existe posición abierta -> Escalamiento Macro P2 para Breakeven P3
        existing_p1 = active_same_side[0]
        p1_entry = float(existing_p1.get('avg_entry_price') or existing_p1.get('entry_price') or 0.0)
        p1_qty = float(existing_p1.get('size') or existing_p1.get('lots') or existing_p1.get('quantity') or 0.01)
        tranche_count = int(existing_p1.get('erep_purchases_count', 0) or existing_p1.get('tranches_count', 1))

        # Restricción 1: Máximo 2 tranches en total (P1 + P2 Macro)
        if tranche_count >= 2:
            return {
                'trigger': False,
                'reason': f"Tope de tranches alcanzado ({tranche_count}/2). No se permite promediar una tercera vez."
            }

        # Restricción 2: Distancia mínima de 1.5%
        if p1_entry > 0:
            if side_suggested == 'short':
                dist_pct = (current_price - p1_entry) / p1_entry * 100.0
            else:
                dist_pct = (p1_entry - current_price) / p1_entry * 100.0

            if dist_pct < 1.5:
                return {
                    'trigger': False,
                    'reason': f"Distancia insuficiente ({dist_pct:.2f}% < 1.5% requerido respecto a P1 entrada ${p1_entry:.4f})."
                }

        # Cálculo de P2 y nuevo Breakeven P3
        p2_qty = p1_qty  # Multiplicador 1:1 calibrado
        new_total_qty = p1_qty + p2_qty
        p3_avg = ((p1_entry * p1_qty) + (current_price * p2_qty)) / new_total_qty

        return {
            'trigger': True,
            'action': 'SCALE_IN_P2_MACRO',
            'order_type': 'MARKET',
            'side': side_suggested,
            'timeframe': hit_tf,
            'level': level_touched,
            'level_price': level_price,
            'p1_entry': p1_entry,
            'p1_qty': p1_qty,
            'p2_qty': p2_qty,
            'p3_weighted_breakeven': round(p3_avg, 5),
            'rule_code': f"MACRO_P2_{hit_tf.upper()}_{level_touched}",
            'reason': f"Refuerzo Macro P2 en {hit_tf.upper()} ({level_touched} @ {current_price:.4f}). Nuevo Breakeven P3 = ${p3_avg:.4f}. Cierre total en retroceso."
        }
