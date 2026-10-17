"""
eTrade v6.0 — TRAP SHIELD & INTRADAY ALPHA PRIORITY ENGINE
===========================================================
Módulo de protección institucional contra trampas de apertura ("Gap & Crap")
y clasificador de candidatos de ALTO CRECIMIENTO INTRADÍA (Potencial >= +5% a +50%+).

Funcionalidades Clave:
1. Trap Shield (Filtro Anti-Trampas):
   - Excluye Gaps Excesivos (> +60% a +400%) propensos a desplome.
   - Excluye velas rojas de apertura que perforan el mínimo del Opening Range (ORB_Low).
   - Excluye activos que cotizan por debajo del VWAP intradía.
   - Excluye agotamiento o sequía de volumen institucional.

2. Intraday Alpha Sweet Spot:
   - Detecta el rango de oro de apertura (-3% a +35% de Gap).
   - Valida Combustible RVOL (>= 2.5x a 5.0x+).
   - Calcula la Ganancia Potencial Intradía hacia UPPER_5 / UPPER_6 o expansión de ADR.
   - Otorga BOOST de ALTA PRIORIDAD inmediata (Rank >= 98.0) para compra en sesión regular.
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from app.core.logger import log_info, log_warning, log_error

MODULE = "TRAP_SHIELD"


def _safe_series(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Extrae una serie de columna insensible a mayúsculas/minúsculas."""
    if col_name in df.columns:
        return pd.to_numeric(df[col_name], errors='coerce')
    cap = col_name.capitalize()
    if cap in df.columns:
        return pd.to_numeric(df[cap], errors='coerce')
    upper = col_name.upper()
    if upper in df.columns:
        return pd.to_numeric(df[upper], errors='coerce')
    return pd.Series(dtype=float)


def calculate_intraday_vwap(df_intraday: Optional[pd.DataFrame]) -> float:
    """
    Calcula el Volume-Weighted Average Price (VWAP) de la sesión regular:
    VWAP = sum(Typical_Price * Volume) / sum(Volume)
    Typical_Price = (High + Low + Close) / 3
    """
    if df_intraday is None or len(df_intraday) < 2:
        return 0.0

    try:
        high = _safe_series(df_intraday, 'high')
        low = _safe_series(df_intraday, 'low')
        close = _safe_series(df_intraday, 'close')
        volume = _safe_series(df_intraday, 'volume')

        if volume.sum() <= 0:
            return float(close.iloc[-1]) if len(close) > 0 else 0.0

        typical_price = (high + low + close) / 3.0
        pv = typical_price * volume
        cum_pv = pv.sum()
        cum_vol = volume.sum()

        if cum_vol > 0:
            return float(cum_pv / cum_vol)
        return float(close.iloc[-1])
    except Exception as e:
        log_warning(MODULE, f"Error calculando VWAP: {e}")
        return 0.0


def evaluate_opening_range_5m(df_5m: Optional[pd.DataFrame]) -> dict:
    """
    Evalúa las primeras velas de la sesión (Opening Range Breakout - ORB):
    - Identifica si la vela de apertura cerró roja (Close < Open).
    - Identifica el máximo y mínimo de los primeros minutos (ORB_High, ORB_Low).
    - Mide si el precio actual perforó el soporte inicial (ORB_Low).
    """
    if df_5m is None or len(df_5m) < 1:
        return {
            'has_orb': False,
            'first_candle_red': False,
            'orb_high': 0.0,
            'orb_low': 0.0,
            'price_below_orb_low': False,
            'reason': 'Sin velas 5m'
        }

    try:
        open_s = _safe_series(df_5m, 'open')
        high_s = _safe_series(df_5m, 'high')
        low_s = _safe_series(df_5m, 'low')
        close_s = _safe_series(df_5m, 'close')

        first_open = float(open_s.iloc[0])
        first_close = float(close_s.iloc[0])
        first_candle_red = (first_close < first_open)

        # Primeras 3 velas (15 min) o las disponibles
        candles_window = min(3, len(df_5m))
        orb_high = float(high_s.iloc[:candles_window].max())
        orb_low = float(low_s.iloc[:candles_window].min())

        cur_close = float(close_s.iloc[-1])
        price_below_orb_low = (cur_close < orb_low * 0.997)

        # Detección de Recuperación / Giro de Apertura (ORB Bullish Recovery):
        # Si la 1ra vela fue roja pero dentro de las primeras 3-6 velas (primeros 15-30 min de sesión):
        # - La vela actual (2da o 3ra) es verde (cur_close > cur_open)
        # - El precio recupera y supera el Open de la sesión (cur_close >= first_open * 0.998)
        # - O la 2da/3ra vela rompe el High de la 1ra vela
        # - Con volumen sustancial (cur_vol >= 200,000 o RVOL >= 1.5)
        vol_s = _safe_series(df_5m, 'volume')
        cur_open = float(open_s.iloc[-1])
        cur_vol = float(vol_s.iloc[-1]) if len(vol_s) > 0 else 0
        first_vol = float(vol_s.iloc[0]) if len(vol_s) > 0 else 1
        rvol_5m = cur_vol / max(1.0, first_vol) if len(vol_s) >= 2 else 1.0

        orb_bullish_recovery = False
        if len(df_5m) >= 2 and len(df_5m) <= 6:
            recovering_open = (cur_close >= first_open * 0.998) and (cur_close > cur_open)
            breaking_first_high = (cur_close > float(high_s.iloc[0]))
            has_vol = (cur_vol >= 200_000) or (rvol_5m >= 1.5) or (cur_vol >= 0.05 * first_vol and cur_vol >= 100_000)
            if (recovering_open or breaking_first_high) and has_vol:
                orb_bullish_recovery = True

        return {
            'has_orb': True,
            'first_candle_red': first_candle_red,
            'orb_high': round(orb_high, 3),
            'orb_low': round(orb_low, 3),
            'price_below_orb_low': price_below_orb_low,
            'orb_bullish_recovery': orb_bullish_recovery,
            'cur_close': cur_close,
            'reason': f"ORB=[{orb_low:.2f} - {orb_high:.2f}], Vela1={'ROJA 🔴' if first_candle_red else 'VERDE 🟢'}{', RECOVERY 🟢' if orb_bullish_recovery else ''}"
        }
    except Exception as e:
        log_warning(MODULE, f"Error evaluando ORB 5m: {e}")
        return {
            'has_orb': False,
            'first_candle_red': False,
            'orb_high': 0.0,
            'orb_low': 0.0,
            'price_below_orb_low': False,
            'reason': f"Excepción ORB: {e}"
        }


def calculate_intraday_potential_growth(
    current_price: float,
    bands_15m: Optional[dict] = None,
    adr_pct: float = 4.0,
    consumed_pct: float = 30.0
) -> float:
    """
    Calcula la ganancia potencial intradía estimada (%):
    1. Distancia hacia UPPER_5 de 15m / 1H.
    2. Espacio remanente del ADR diario.
    """
    if current_price <= 0:
        return 5.0

    target_price = 0.0
    if bands_15m and 'upper_5' in bands_15m:
        u5 = float(bands_15m.get('upper_5', 0))
        if u5 > current_price:
            target_price = u5

    if target_price > current_price:
        potential_pct = (target_price - current_price) / current_price * 100.0
        return round(max(3.0, min(150.0, potential_pct)), 1)

    # Si no hay banda superior o ya la superó, basar en ADR restante
    rem_adr = max(0.0, (100.0 - consumed_pct) / 100.0 * adr_pct)
    return round(max(5.0, min(80.0, rem_adr * 1.5)), 1)


def evaluate_trap_shield(
    current_price: float,
    prev_close: float,
    open_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    rvol: float = 1.0,
    news_tier: int = 2,
    adr_pct: float = 4.0,
    consumed_pct: float = 30.0,
    bands_15m: Optional[dict] = None,
) -> dict:
    """
    EVALUADOR PRINCIPAL: TRAP SHIELD & INTRADAY ALPHA CANDIDATE
    
    Salida:
    - is_trap: bool (True si la acción es una trampa de apertura)
    - trap_type: str ("EXCESSIVE_GAP_FADE", "OPENING_RANGE_BREAK_DOWN", "BELOW_VWAP", "NONE")
    - trap_reason: str
    - gap_pct: float
    - is_sweet_spot: bool (-3% a +35% de Gap)
    - is_intraday_alpha: bool (Candidato de compra prioritaria en el día)
    - growth_potential_pct: float (Potencial de ganancia >= 5%)
    - priority_rank_boost: float (98.5 si califica)
    """
    if current_price <= 0:
        return {
            'is_trap': False,
            'trap_type': 'NONE',
            'trap_reason': 'Precio inválido',
            'gap_pct': 0.0,
            'is_sweet_spot': False,
            'is_intraday_alpha': False,
            'growth_potential_pct': 0.0,
            'priority_rank_boost': 0.0
        }

    # 1. Cálculo de Gap de Apertura
    base_prev = prev_close if prev_close > 0 else (open_price if open_price > 0 else current_price)
    eff_open = open_price if open_price > 0 else current_price
    gap_pct = ((eff_open - base_prev) / base_prev * 100.0) if base_prev > 0 else 0.0

    # 2. VWAP Intradía
    df_intraday = df_5m if (df_5m is not None and len(df_5m) >= 2) else df_15m
    vwap = calculate_intraday_vwap(df_intraday)
    is_below_vwap = (vwap > 0 and current_price < vwap * 0.995)

    # 3. Opening Range 5m
    orb_info = evaluate_opening_range_5m(df_5m)

    # 4. Potencial de Ganancia Intradía
    growth_potential_pct = calculate_intraday_potential_growth(
        current_price=current_price,
        bands_15m=bands_15m,
        adr_pct=adr_pct,
        consumed_pct=consumed_pct
    )

    # ════════════════════════════════════════════════════════════
    # REGLAS DE DESCARTE DE TRAMPAS (TRAP SHIELD)
    # ════════════════════════════════════════════════════════════

    # TRAMPA 1: GAP EXCESIVO DESINFLÁNDOSE (> +60% con colapso o falta de catalizador Nivel 1)
    # Ejemplo AEMD (+493% gap que cae -20%), PDSB día 1 (+121% que colapsa)
    if gap_pct > 60.0:
        # Si el gap es astronómico (> 60%) y el precio ya cotiza por debajo del Open o del VWAP
        if current_price < eff_open * 0.98 or is_below_vwap:
            return {
                'is_trap': True,
                'trap_type': 'EXCESSIVE_GAP_FADE',
                'trap_reason': f"Trampa Gap Masivo (+{gap_pct:.1f}%): Cotiza bajo Open (${eff_open:.2f}) o VWAP (${vwap:.2f}). Descarga masiva.",
                'gap_pct': round(gap_pct, 1),
                'is_sweet_spot': False,
                'is_intraday_alpha': False,
                'growth_potential_pct': growth_potential_pct,
                'priority_rank_boost': 0.0,
                'vwap': round(vwap, 3)
            }
        
        # Si no tiene catalizador de máximo impacto (Nivel 1: FDA / M&A), un gap > 80% es trampa estadística segura
        if gap_pct > 80.0 and news_tier > 1:
            return {
                'is_trap': True,
                'trap_type': 'EXCESSIVE_GAP_NO_CATALYST',
                'trap_reason': f"Gap de +{gap_pct:.1f}% sin catalizador de Nivel 1 (Tier={news_tier}). Riesgo extremo de dilución.",
                'gap_pct': round(gap_pct, 1),
                'is_sweet_spot': False,
                'is_intraday_alpha': False,
                'growth_potential_pct': growth_potential_pct,
                'priority_rank_boost': 0.0,
                'vwap': round(vwap, 3)
            }

    # TRAMPA 2: APERTURA ROJA CON QUIEBRE DE SOPORTE ORB (Gap & Crap clásico)
    # La vela de apertura abrió arriba pero cerró roja y el precio perforó el mínimo de apertura
    if gap_pct > 10.0 and orb_info['has_orb']:
        # EXCEPCIÓN ORB_BULLISH_RECOVERY: Si la 2da o 3ra vela de 5m (primeros 15-30 min) recupera sobre el Open con volumen,
        # NO es trampa: es un shakeout matutino con giro comprador inmediato
        if orb_info.get('orb_bullish_recovery', False):
            log_info(MODULE, f"🟢 ORB Bullish Recovery detectado: Precio (${current_price:.2f}) recuperó Open con volumen. Veto de trampa anulado.")
        elif orb_info['first_candle_red'] and orb_info['price_below_orb_low']:
            return {
                'is_trap': True,
                'trap_type': 'OPENING_RANGE_BREAK_DOWN',
                'trap_reason': f"Gap & Crap: Vela 1 roja con perforación de soporte inicial (${orb_info['orb_low']:.2f}).",
                'gap_pct': round(gap_pct, 1),
                'is_sweet_spot': False,
                'is_intraday_alpha': False,
                'growth_potential_pct': growth_potential_pct,
                'priority_rank_boost': 0.0,
                'vwap': round(vwap, 3)
            }

    # TRAMPA 3: COTIZA CLARAMENTE POR DEBAJO DEL VWAP CON GAP ALTO
    if gap_pct >= 20.0 and is_below_vwap:
        # Si está en recuperación ORB y el precio actual ya superó el Open o está sobre/cerca de VWAP
        if orb_info.get('orb_bullish_recovery', False) or (current_price >= eff_open * 0.998):
            log_info(MODULE, f"🟢 Excepción Below VWAP: En recuperación ORB superando Open (${eff_open:.2f}). Veto anulado.")
        else:
            return {
                'is_trap': True,
                'trap_type': 'BELOW_VWAP',
                'trap_reason': f"Precio (${current_price:.2f}) bajo VWAP (${vwap:.2f}) con Gap de +{gap_pct:.1f}%. Compradores atrapados.",
                'gap_pct': round(gap_pct, 1),
                'is_sweet_spot': False,
                'is_intraday_alpha': False,
                'growth_potential_pct': growth_potential_pct,
                'priority_rank_boost': 0.0,
                'vwap': round(vwap, 3)
            }

    # ════════════════════════════════════════════════════════════
    # ZONA DE ORO (SWEET SPOT) & ALTA PRIORIDAD INTRADÍA
    # ════════════════════════════════════════════════════════════
    # El rango ideal: Gaps entre -3% y +35% (o hasta +45% con combustible)
    is_sweet_spot = (-3.0 <= gap_pct <= 35.0) or (35.0 < gap_pct <= 50.0 and rvol >= 10.0)

    # Condiciones para Calificar a ALTA PRIORIDAD INTRADÍA (Alpha Runner):
    # 1. No es trampa.
    # 2. Está en el Sweet Spot (todo el combustible por recorrer en sesión regular).
    # 3. RVOL fuerte (>= 2.5x).
    # 4. Precio sobre VWAP (o al menos sobre Open si VWAP aún no estabiliza).
    # 5. Potencial de ganancia >= 5.0%.
    price_healthy = (current_price >= vwap * 0.998) if vwap > 0 else (current_price >= eff_open * 0.99)
    orb_healthy = not orb_info.get('price_below_orb_low', False)

    is_intraday_alpha = (
        is_sweet_spot and
        (rvol >= 2.5) and
        price_healthy and
        orb_healthy and
        (growth_potential_pct >= 5.0)
    )

    alpha_score = 50
    if is_intraday_alpha:
        # Puntaje de 75 a 99
        alpha_score = 80
        if rvol >= 5.0: alpha_score += 10
        if current_price > eff_open: alpha_score += 5
        if growth_potential_pct >= 10.0: alpha_score += 4
        alpha_score = min(99, alpha_score)

    priority_boost = 98.5 if is_intraday_alpha else 0.0

    return {
        'is_trap': False,
        'trap_type': 'NONE',
        'trap_reason': 'Validación limpia (Sin trampa de apertura)',
        'gap_pct': round(gap_pct, 1),
        'is_sweet_spot': is_sweet_spot,
        'is_intraday_alpha': is_intraday_alpha,
        'intraday_alpha_score': alpha_score,
        'growth_potential_pct': growth_potential_pct,
        'priority_rank_boost': priority_boost,
        'vwap': round(vwap, 3) if vwap > 0 else current_price,
        'orb_info': orb_info,
        'summary': (
            f"TrapShield=CLEAR ✅ | Gap=+{gap_pct:.1f}% | "
            f"AlphaIntraday={'SÍ 🚀 (Rank 98.5)' if is_intraday_alpha else 'NO'} | "
            f"Potencial=+{growth_potential_pct:.1f}% | RVOL={rvol:.1f}x"
        )
    }
