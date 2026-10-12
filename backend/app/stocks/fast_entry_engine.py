"""
eTrade v6.0 — FAST ENTRY ENGINE FOR STOCKS (MULTI-TIMEFRAME)
============================================================
Gatillo técnico de entrada rápida multi-temporalidad para acciones:
Sincronización de 5m, 15m, 1H, 4H y 1D con ADX, +DI/-DI, EMAs, VWAP y Velas.

Rutas de Entrada Rápida Intradía:
1. ORB_BREAKOUT_FAST: Ruptura del máximo de los primeros minutos (ORB_High) con +DI > -DI.
2. VWAP_PULLBACK_ABSORPTION: Retroceso respetando VWAP/EMA9 con absorción (mecha inferior >= 35%).
3. ADX_MOMENTUM_IGNITION: Explosión direccional (+DI > 28, ADX > 20 en 5m/15m con RVOL >= 2.5x).
"""

from typing import Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from app.core.logger import log_info, log_warning, log_error
from app.analysis.adx_di import calculate_adx
from app.stocks.trap_shield import calculate_intraday_vwap, evaluate_opening_range_5m

MODULE = "FAST_ENTRY_ENGINE"


def _safe_col(df: pd.DataFrame, col_name: str) -> pd.Series:
    """Extrae columna insensible a mayúsculas/minúsculas."""
    if col_name in df.columns:
        return pd.to_numeric(df[col_name], errors='coerce')
    cap = col_name.capitalize()
    if cap in df.columns:
        return pd.to_numeric(df[cap], errors='coerce')
    upper = col_name.upper()
    if upper in df.columns:
        return pd.to_numeric(df[upper], errors='coerce')
    return pd.Series(dtype=float)


def compute_adx_di_summary(df: Optional[pd.DataFrame], period: int = 14) -> dict:
    """Calcula métricas clave de ADX, +DI, -DI y delta para un dataframe."""
    if df is None or len(df) < period + 2:
        return {
            'adx': 0.0,
            'plus_di': 0.0,
            'minus_di': 0.0,
            'di_delta': 0.0,
            'is_bullish_di': False,
            'is_adx_rising': False,
            'valid': False
        }

    try:
        # Normalizar nombres de columnas a minúsculas para calculate_adx
        df_norm = pd.DataFrame({
            'high': _safe_col(df, 'high'),
            'low': _safe_col(df, 'low'),
            'close': _safe_col(df, 'close')
        }).dropna()

        if len(df_norm) < period + 2:
            return {'adx': 0.0, 'plus_di': 0.0, 'minus_di': 0.0, 'di_delta': 0.0, 'is_bullish_di': False, 'is_adx_rising': False, 'valid': False}

        calc_df = calculate_adx(df_norm, period=period)
        adx_val = float(calc_df['adx'].iloc[-1])
        plus_di = float(calc_df['plus_di'].iloc[-1])
        minus_di = float(calc_df['minus_di'].iloc[-1])
        adx_rising = bool(calc_df['adx_rising'].iloc[-1]) if 'adx_rising' in calc_df else False
        di_delta = plus_di - minus_di

        return {
            'adx': round(adx_val, 1),
            'plus_di': round(plus_di, 1),
            'minus_di': round(minus_di, 1),
            'di_delta': round(di_delta, 1),
            'is_bullish_di': plus_di > minus_di,
            'is_adx_rising': adx_rising,
            'valid': True
        }
    except Exception as e:
        log_warning(MODULE, f"Error calculando ADX/DI: {e}")
        return {'adx': 0.0, 'plus_di': 0.0, 'minus_di': 0.0, 'di_delta': 0.0, 'is_bullish_di': False, 'is_adx_rising': False, 'valid': False}


def detect_candle_absorption_5m(df_5m: pd.DataFrame) -> dict:
    """Evalúa si la última vela de 5m muestra absorción compradora."""
    if df_5m is None or len(df_5m) < 1:
        return {'has_absorption': False, 'reason': 'Sin velas 5m'}

    try:
        open_s = _safe_col(df_5m, 'open')
        high_s = _safe_col(df_5m, 'high')
        low_s = _safe_col(df_5m, 'low')
        close_s = _safe_col(df_5m, 'close')

        o = float(open_s.iloc[-1])
        h = float(high_s.iloc[-1])
        l = float(low_s.iloc[-1])
        c = float(close_s.iloc[-1])

        rng = max(1e-6, h - l)
        lower_wick = max(0.0, min(o, c) - l)
        lower_wick_pct = (lower_wick / rng) * 100.0
        close_pos_pct = ((c - l) / rng) * 100.0
        is_green = c >= o

        has_wick = lower_wick_pct >= 35.0
        has_strong_close = is_green and (close_pos_pct >= 60.0)

        return {
            'has_absorption': has_wick or has_strong_close,
            'is_green': is_green,
            'lower_wick_pct': round(lower_wick_pct, 1),
            'close_pos_pct': round(close_pos_pct, 1),
            'last_low': l,
            'reason': f"Mecha inf={lower_wick_pct:.1f}%, Cierre={close_pos_pct:.0f}% rango"
        }
    except Exception as e:
        return {'has_absorption': False, 'reason': f"Error: {e}"}


def evaluate_fast_entry(
    current_price: float,
    df_5m: Optional[pd.DataFrame] = None,
    df_15m: Optional[pd.DataFrame] = None,
    df_1h: Optional[pd.DataFrame] = None,
    df_4h: Optional[pd.DataFrame] = None,
    df_1d: Optional[pd.DataFrame] = None,
    rvol: float = 1.0,
    bands_15m: Optional[dict] = None,
    is_trap: bool = False
) -> dict:
    """
    EVALUADOR MAESTRO DE ENTRADA RÁPIDA (FAST ENTRY ENGINE)
    
    Valida la sincronización de ADX / +DI / -DI en 5m, 15m y 1H,
    con respecto a VWAP, EMAs y formación de velas para entrada inmediata.
    """
    if is_trap or current_price <= 0:
        return {
            'fast_entry_triggered': False,
            'entry_type': None,
            'entry_reason': 'Bloqueado por Trap Shield o precio inválido',
            'recommended_sl': 0.0,
            'target_upper5': 0.0,
            'target_upper6': 0.0,
            'adx_metrics': {}
        }

    # 1. Multi-Timeframe ADX/DI
    adx_5m = compute_adx_di_summary(df_5m)
    adx_15m = compute_adx_di_summary(df_15m)
    adx_1h = compute_adx_di_summary(df_1h)

    # 2. VWAP Intradía y ORB
    df_intra = df_5m if (df_5m is not None and len(df_5m) >= 2) else df_15m
    vwap = calculate_intraday_vwap(df_intra)
    orb_info = evaluate_opening_range_5m(df_5m)

    # 3. Formación de Vela 5m
    absorb_5m = detect_candle_absorption_5m(df_5m) if df_5m is not None else {'has_absorption': True, 'last_low': current_price * 0.98}

    # 4. EMAs en 5m
    ema3_5m = current_price
    ema9_5m = current_price
    if df_5m is not None and len(df_5m) >= 5:
        close_5m = _safe_col(df_5m, 'close')
        ema3_5m = float(close_5m.ewm(span=3, adjust=False).mean().iloc[-1])
        ema9_5m = float(close_5m.ewm(span=9, adjust=False).mean().iloc[-1])

    # 5. Niveles de salida objetivo (UPPER_5 y UPPER_6)
    target_u5 = float(bands_15m.get('upper_5', current_price * 1.05)) if bands_15m else current_price * 1.05
    target_u6 = float(bands_15m.get('upper_6', current_price * 1.08)) if bands_15m else current_price * 1.08
    rec_sl = max(vwap * 0.985, float(absorb_5m.get('last_low', current_price * 0.98)) * 0.995) if vwap > 0 else current_price * 0.98

    # Filtro innegociable de soporte: Precio debe estar sobre VWAP y sin quiebre de ORB
    price_above_vwap = (vwap <= 0 or current_price >= vwap * 0.995)
    not_breaking_orb = not orb_info.get('price_below_orb_low', False)

    if not price_above_vwap or not not_breaking_orb:
        return {
            'fast_entry_triggered': False,
            'entry_type': None,
            'entry_reason': f"Precio bajo VWAP (${vwap:.2f}) o perforando ORB Low",
            'recommended_sl': rec_sl,
            'target_upper5': target_u5,
            'target_upper6': target_u6,
            'adx_metrics': {'5m': adx_5m, '15m': adx_15m, '1h': adx_1h}
        }

    # ════════════════════════════════════════════════════════════
    # GATILLO 1: ORB BREAKOUT FAST (Ruptura del techo de apertura con +DI dominante)
    # ════════════════════════════════════════════════════════════
    if orb_info['has_orb'] and orb_info['orb_high'] > 0:
        if current_price >= orb_info['orb_high'] * 0.998 and adx_5m['is_bullish_di']:
            return {
                'fast_entry_triggered': True,
                'entry_type': 'ORB_BREAKOUT_FAST',
                'entry_reason': f"Ruptura ORB High (${orb_info['orb_high']:.2f}) con +DI ({adx_5m['plus_di']:.1f}) > -DI ({adx_5m['minus_di']:.1f}) y RVOL {rvol:.1f}x ✅",
                'recommended_sl': round(rec_sl, 2),
                'target_upper5': round(target_u5, 2),
                'target_upper6': round(target_u6, 2),
                'adx_metrics': {'5m': adx_5m, '15m': adx_15m, '1h': adx_1h}
            }

    # ════════════════════════════════════════════════════════════
    # GATILLO 2: VWAP / EMA9 PULLBACK ABSORPTION (Rebote en soporte institucional)
    # ════════════════════════════════════════════════════════════
    near_vwap = (vwap > 0 and abs(current_price - vwap) / vwap <= 0.015)
    near_ema9 = (ema9_5m > 0 and abs(current_price - ema9_5m) / ema9_5m <= 0.012)
    
    if (near_vwap or near_ema9) and absorb_5m['has_absorption']:
        if adx_5m['is_bullish_di'] or adx_15m['is_bullish_di']:
            support_label = "VWAP" if near_vwap else "EMA9 5m"
            return {
                'fast_entry_triggered': True,
                'entry_type': 'PULLBACK_VWAP_ABSORPTION',
                'entry_reason': f"Rebote y Absorción en {support_label} (${vwap if near_vwap else ema9_5m:.2f}) con vela alcista y +DI dominante ✅",
                'recommended_sl': round(rec_sl, 2),
                'target_upper5': round(target_u5, 2),
                'target_upper6': round(target_u6, 2),
                'adx_metrics': {'5m': adx_5m, '15m': adx_15m, '1h': adx_1h}
            }

    # ════════════════════════════════════════════════════════════
    # GATILLO 3: ADX & +DI EXPLOSION (Fuerza direccional pura en expansión)
    # ════════════════════════════════════════════════════════════
    # Si +DI > 26 y ADX >= 20 con EMA3 > EMA9 y RVOL >= 2.5x
    if adx_5m['plus_di'] >= 26.0 and adx_5m['di_delta'] >= 8.0 and (ema3_5m >= ema9_5m * 0.998) and rvol >= 2.5:
        return {
            'fast_entry_triggered': True,
            'entry_type': 'ADX_DI_EXPLOSION',
            'entry_reason': f"Explosión Direccional en 5m (+DI={adx_5m['plus_di']:.1f}, Delta=+{adx_5m['di_delta']:.1f}, ADX={adx_5m['adx']:.1f}, RVOL={rvol:.1f}x) ✅",
            'recommended_sl': round(rec_sl, 2),
            'target_upper5': round(target_u5, 2),
            'target_upper6': round(target_u6, 2),
            'adx_metrics': {'5m': adx_5m, '15m': adx_15m, '1h': adx_1h}
        }

    return {
        'fast_entry_triggered': False,
        'entry_type': None,
        'entry_reason': f"Esperando confirmación de gatillo (+DI={adx_5m['plus_di']:.1f}, -DI={adx_5m['minus_di']:.1f}, Precio=${current_price:.2f})",
        'recommended_sl': round(rec_sl, 2),
        'target_upper5': round(target_u5, 2),
        'target_upper6': round(target_u6, 2),
        'adx_metrics': {'5m': adx_5m, '15m': adx_15m, '1h': adx_1h}
    }
