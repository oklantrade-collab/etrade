"""
eTrade v6.0 — ADR & Volatility Fuel Gate for Stocks
=====================================================
Motor de validación de Volatilidad Diaria (ADR), Consumo de Rango,
Compresión de Bollinger Bandwidth y Combustible Institucional.

Previene ingresos en activos aletargados (como SBS o NU) con movimientos horizontales,
bandas planas y volumen fantasma, asegurando que las compras HOT solo entren en
acciones con oscilación real y combustible de ruptura (como RXRX o SMCI).
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List

from app.core.logger import log_info, log_warning, log_error

MODULE = "ADR_VOLATILITY_GATE"


def calculate_adr(df_1d: Optional[pd.DataFrame], period: int = 14) -> dict:
    """
    Calcula el ADR (Average Daily Range) histórico en velas de 1D
    y determina el consumo del rango diario actual.
    """
    if df_1d is None or len(df_1d) < 3:
        return {
            'adr_pct': 0.0,
            'adr_usd': 0.0,
            'today_range_usd': 0.0,
            'today_range_pct': 0.0,
            'consumed_pct': 0.0,
            'has_room': True,
            'reason': 'Datos 1D insuficientes'
        }

    try:
        df_c = df_1d.copy()
        high = df_c['high']
        low = df_c['low']
        close = df_c['close']

        # Considerar hasta 'period' velas previas cerradas
        lookback = min(period, len(df_c) - 1) if len(df_c) > 1 else 1
        historical_high = high.iloc[-lookback - 1:-1] if len(df_c) > lookback else high.iloc[:-1]
        historical_low = low.iloc[-lookback - 1:-1] if len(df_c) > lookback else low.iloc[:-1]
        historical_close = close.iloc[-lookback - 1:-1] if len(df_c) > lookback else close.iloc[:-1]

        if len(historical_close) == 0:
            historical_high = high
            historical_low = low
            historical_close = close

        daily_ranges_pct = ((historical_high - historical_low) / historical_close.replace(0, np.nan)) * 100.0
        daily_ranges_usd = (historical_high - historical_low)

        adr_pct = float(daily_ranges_pct.dropna().mean()) if len(daily_ranges_pct.dropna()) > 0 else 0.0
        adr_usd = float(daily_ranges_usd.dropna().mean()) if len(daily_ranges_usd.dropna()) > 0 else 0.0

        # Rango de la vela actual (hoy)
        today_h = float(high.iloc[-1])
        today_l = float(low.iloc[-1])
        today_c = float(close.iloc[-1])
        today_range_usd = max(0.0, today_h - today_l)
        today_range_pct = (today_range_usd / today_c * 100.0) if today_c > 0 else 0.0

        consumed_pct = (today_range_usd / adr_usd * 100.0) if adr_usd > 0 else 0.0
        consumed_pct = min(250.0, max(0.0, consumed_pct))

        # Espacio remanente: Si ha consumido menos del 80% de su ADR
        has_room = (consumed_pct < 80.0)

        return {
            'adr_pct': round(adr_pct, 2),
            'adr_usd': round(adr_usd, 4),
            'today_range_usd': round(today_range_usd, 4),
            'today_range_pct': round(today_range_pct, 2),
            'consumed_pct': round(consumed_pct, 1),
            'has_room': has_room,
            'reason': 'OK'
        }

    except Exception as e:
        log_error(MODULE, f"Error calculando ADR diario: {e}")
        return {
            'adr_pct': 0.0,
            'adr_usd': 0.0,
            'today_range_usd': 0.0,
            'today_range_pct': 0.0,
            'consumed_pct': 0.0,
            'has_room': True,
            'reason': f'Error: {e}'
        }


def calculate_bollinger_bandwidth_15m(df_15m: Optional[pd.DataFrame], period: int = 20) -> dict:
    """
    Calcula el Ancho de Banda de Bollinger (Bandwidth) en 15m y su pendiente,
    para detectar compresión lateral muerta ('dead chop') vs expansión real.
    """
    if df_15m is None or len(df_15m) < period:
        return {
            'bandwidth_pct': 2.5,
            'bandwidth_slope': 0.0,
            'is_dead_compression': False,
            'is_expanding': False,
            'bb_upper': 0.0,
            'bb_lower': 0.0,
            'bb_middle': 0.0
        }

    try:
        c = df_15m['close'].astype(float)
        sma = c.rolling(period).mean()
        std = c.rolling(period).std()

        up = sma + (2.0 * std)
        lo = sma - (2.0 * std)

        bw = ((up - lo) / sma.replace(0, np.nan)) * 100.0
        bw_now = float(bw.iloc[-1])
        bw_prev = float(bw.iloc[-2]) if len(bw) >= 2 else bw_now
        bw_slope = bw_now - bw_prev

        up_now = float(up.iloc[-1])
        up_prev = float(up.iloc[-2]) if len(up) >= 2 else up_now
        up_slope = up_now - up_prev

        is_dead_compression = (bw_now < 2.0 and bw_slope <= 0.05 and up_slope <= 0.0)
        is_expanding = (bw_slope > 0.05 and up_slope > 0.0)

        return {
            'bandwidth_pct': round(bw_now, 2),
            'bandwidth_slope': round(bw_slope, 3),
            'is_dead_compression': is_dead_compression,
            'is_expanding': is_expanding,
            'bb_upper': round(up_now, 4),
            'bb_lower': round(float(lo.iloc[-1]), 4),
            'bb_middle': round(float(sma.iloc[-1]), 4)
        }

    except Exception as e:
        log_error(MODULE, f"Error calculando Bollinger Bandwidth 15m: {e}")
        return {
            'bandwidth_pct': 2.5,
            'bandwidth_slope': 0.0,
            'is_dead_compression': False,
            'is_expanding': False,
            'bb_upper': 0.0,
            'bb_lower': 0.0,
            'bb_middle': 0.0
        }


def evaluate_adr_and_volatility_gate(
    df_1d: Optional[pd.DataFrame],
    df_15m: Optional[pd.DataFrame],
    current_price: float,
    rule_code: str = "",
    group_name: str = "hot",
    rvol_15m_override: Optional[float] = None
) -> dict:
    """
    GUARDIA TRANSVERSAL DE VOLATILIDAD, ESPACIO REMANENTE Y COMBUSTIBLE DE RUPTURA.
    
    Aplica filtros estrictos para órdenes HOT (intradía / momentum):
    1. ADR Mínimo >= 3.5% (descarta activos lentos/estancados como SBS y NU).
    2. ADR Consumido < 80.0% (asegura que haya espacio libre en el tanque para correr).
       Si ADR Consumido >= 80%, exige RVOL institucional >= 2.0x para justificar ruptura.
    3. Anti-Dead Compression (Bandwidth 15m >= 2.0% o expansión confirmada).
    4. Anti-Vela Fantasma: Volumen mínimo por vela en 15m >= 5,000 acciones.
    """
    adr_info = calculate_adr(df_1d, period=14)
    bb_info = calculate_bollinger_bandwidth_15m(df_15m, period=20)

    candle_vol_15m = 0.0
    rvol_15m = 1.0
    if df_15m is not None and len(df_15m) >= 2:
        vol_col = df_15m['volume'] if 'volume' in df_15m.columns else pd.Series([0.0]*len(df_15m))
        candle_vol_15m = float(vol_col.iloc[-1])
        vol_mean = float(vol_col.rolling(20, min_periods=3).mean().iloc[-1]) if len(vol_col) >= 3 else candle_vol_15m
        rvol_15m = (candle_vol_15m / vol_mean) if vol_mean > 0 else 1.0

    if rvol_15m_override is not None:
        rvol_15m = float(rvol_15m_override)

    is_hot_or_scalp = (
        "hot" in group_name.lower() or
        "scalp" in group_name.lower() or
        "hot" in rule_code.lower() or
        "bb_pullback" in rule_code.lower() or
        "dip_buy" in rule_code.lower()
    )

    failures: List[str] = []
    adr_pct = adr_info['adr_pct']
    consumed_pct = adr_info['consumed_pct']
    bw_pct = bb_info['bandwidth_pct']
    is_dead = bb_info['is_dead_compression']
    is_expanding = bb_info['is_expanding']

    # ── VALIDACIÓN PARA REGLAS HOT ──
    if is_hot_or_scalp:
        # 1. Filtro ADR Mínimo (Volatilidad Estructural Diaria)
        # Activos con ADR < 3.5% se mueven muy poco para generar ganancias intradía rentables
        if adr_pct > 0 and adr_pct < 3.50:
            failures.append(
                f"ADR 14D insuficiente ({adr_pct:.2f}% < 3.50%): Activo aletargado sin volatilidad intradía rentable."
            )

        # 2. Filtro de ADR Consumido (Espacio Remanente)
        # Si ya consumió >= 80% de su rango diario promedio, no hay espacio para comprar
        # a menos que haya un volumen extraordinario (RVOL >= 2.0x) que indique ruptura de régimen.
        if consumed_pct >= 80.0 and rvol_15m < 2.0:
            failures.append(
                f"Rango diario agotado ({consumed_pct:.1f}% consumido >= 80.0%): Sin espacio estadístico para correr (RVOL {rvol_15m:.1f}x < 2.0x)."
            )

        # 3. Filtro de Compresión Muerta (Dead Chop en 15m)
        # Bandas aplastadas (< 2.0%) sin expansión activa ni volumen institucional
        if is_dead and not is_expanding and rvol_15m < 1.8:
            failures.append(
                f"Compresión muerta en 15m (Bandwidth {bw_pct:.2f}% < 2.00% plano): Activo horizontal estancado sin expansión."
            )

        # 4. Filtro de Vela Fantasma (Liquidez de la Vela en 15m)
        if candle_vol_15m > 0 and candle_vol_15m < 5000:
            failures.append(
                f"Vela anémica sin combustible institucional ({int(candle_vol_15m)} < 5,000 acciones en 15m)."
            )

    # ── SCORE DE PROBABILIDAD DE RUPTURA (0 a 100) ──
    score = 50
    # Componente 1: Espacio remanente de ADR (0 a 30 pts)
    if consumed_pct < 50.0:
        score += 25
    elif consumed_pct < 75.0:
        score += 15
    elif consumed_pct >= 85.0:
        score -= 20

    # Componente 2: ADR Alto (0 a 20 pts)
    if adr_pct >= 6.0:
        score += 20
    elif adr_pct >= 4.0:
        score += 10
    elif adr_pct < 3.0:
        score -= 20

    # Componente 3: Combustible RVOL 15m (0 a 30 pts)
    if rvol_15m >= 2.0:
        score += 25
    elif rvol_15m >= 1.3:
        score += 15
    elif rvol_15m < 0.8:
        score -= 20

    # Componente 4: Expansión de Bandas (0 a 20 pts)
    if is_expanding:
        score += 15
    elif is_dead:
        score -= 15

    breakout_prob = max(0, min(100, score))

    passed = (len(failures) == 0)

    return {
        'passed': passed,
        'failures': failures,
        'adr_pct': adr_pct,
        'consumed_pct': consumed_pct,
        'has_room': (consumed_pct < 80.0),
        'bandwidth_pct': bw_pct,
        'is_dead_compression': is_dead,
        'is_expanding': is_expanding,
        'candle_vol_15m': candle_vol_15m,
        'rvol_15m': round(rvol_15m, 2),
        'breakout_prob': breakout_prob,
        'summary': (
            f"ADR={adr_pct:.2f}% | Consumido={consumed_pct:.1f}% | "
            f"BW_15m={bw_pct:.2f}% | RVOL_15m={rvol_15m:.2f}x | ProbRuptura={breakout_prob}/100"
        )
    }
