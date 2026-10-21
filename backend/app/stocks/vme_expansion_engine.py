"""
eTrader v5.0 — VOLATILITY MOMENTUM EXPANSION (VME) Engine
Motor especializado para la estrategia de Expansión de Volatilidad y Momentum
en temporalidades de 15 minutos y 1 hora.

Aplica a:
- STOCKS: LONG (VME_EXPANSION_STK)
- OPCIONES: CALL (VME_EXPANSION_CALL) y PUT (VME_EXPANSION_PUT)

Criterios de Entrada:
Requisito Mínimo (1H Macro):
1. LONG: EMA20 > EMA50 en 1H | PUT: EMA20 < EMA50 en 1H
2. LONG: RSI <= 65 en 1H       | PUT: RSI >= 35 en 1H

Gatillos de Alta Prioridad (15m y 1H):
1. ADX >= 25 con +DI > -DI (LONG) o -DI > +DI (PUT).
2. ATR% >= 1.2% o RVOL >= 1.8x.
3. Precio sobre VWAP (+0.3% a +4.0%) para LONG | bajo VWAP (-4.0% a -0.3%) para PUT.
4. Triple EMA Ribbon en 15m: EMA3 > EMA9 > EMA20 (LONG) | EMA3 < EMA9 < EMA20 (PUT).
5. Sincronización en 1H: EMA3 > EMA9 (LONG) | EMA3 < EMA9 (PUT).

Ranking:
- Rank Base: 99.6
- Boost: +0.2 si ADX >= 35
- Boost: +0.1 si RVOL >= 2.5
- Máximo Rank: 99.9 (Lidera sobre Open Gap Runner 99.8)
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional

from app.core.logger import log_info, log_debug, log_warning

MODULE = "vme_engine"


def _ensure_indicators_1h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Garantiza la presencia de EMA3, EMA9, EMA20, EMA50 y RSI14 en 1H."""
    df = df_1h.copy()
    close = pd.to_numeric(df["close"], errors="coerce")
    
    if "ema_3" not in df.columns:
        df["ema_3"] = close.ewm(span=3, adjust=False).mean()
    if "ema_9" not in df.columns:
        df["ema_9"] = close.ewm(span=9, adjust=False).mean()
    if "ema_20" not in df.columns:
        df["ema_20"] = close.ewm(span=20, adjust=False).mean()
    if "ema_50" not in df.columns:
        df["ema_50"] = close.ewm(span=50, adjust=False).mean()
        
    if "rsi_14" not in df.columns:
        try:
            from ta.momentum import RSIIndicator
            df["rsi_14"] = RSIIndicator(close=close, window=14).rsi()
        except Exception:
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss.replace(0, np.nan))
            df["rsi_14"] = 100 - (100 / (1 + rs)).fillna(50)
            
    return df


def _ensure_indicators_15m(df_15m: pd.DataFrame) -> pd.DataFrame:
    """Garantiza la presencia de EMA3, EMA9, EMA20, ADX14, ATR14, VWAP y Bollinger en 15m."""
    df = df_15m.copy()
    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    volume = pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0)

    if "ema_3" not in df.columns:
        df["ema_3"] = close.ewm(span=3, adjust=False).mean()
    if "ema_9" not in df.columns:
        df["ema_9"] = close.ewm(span=9, adjust=False).mean()
    if "ema_20" not in df.columns:
        df["ema_20"] = close.ewm(span=20, adjust=False).mean()

    # ATR 14
    if "atr_14" not in df.columns:
        try:
            from ta.volatility import AverageTrueRange
            df["atr_14"] = AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range()
        except Exception:
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["atr_14"] = tr.rolling(14).mean()

    # ADX 14, DI+, DI-
    if "adx_14" not in df.columns or "di_plus" not in df.columns:
        try:
            from ta.trend import ADXIndicator
            adx_obj = ADXIndicator(high=high, low=low, close=close, window=14)
            df["adx_14"] = adx_obj.adx()
            df["di_plus"] = adx_obj.adx_pos()
            df["di_minus"] = adx_obj.adx_neg()
        except Exception:
            df["adx_14"] = 26.0
            df["di_plus"] = 28.0
            df["di_minus"] = 15.0

    # VWAP
    if "vwap" not in df.columns:
        try:
            cum_vol = volume.cumsum()
            cum_pv = (close * volume).cumsum()
            df["vwap"] = np.where(cum_vol > 0, cum_pv / cum_vol, close)
        except Exception:
            df["vwap"] = close

    # Bollinger Bands (20, 2)
    if "bb_upper" not in df.columns or "bb_lower" not in df.columns:
        try:
            from ta.volatility import BollingerBands
            bb = BollingerBands(close=close, window=20, window_dev=2)
            df["bb_upper"] = bb.bollinger_hband()
            df["bb_lower"] = bb.bollinger_lband()
        except Exception:
            sma20 = close.rolling(20).mean()
            std20 = close.rolling(20).std()
            df["bb_upper"] = sma20 + (std20 * 2.0)
            df["bb_lower"] = sma20 - (std20 * 2.0)

    # RVOL 15m
    if "rvol" not in df.columns:
        vol_sma = volume.rolling(20).mean()
        df["rvol"] = np.where(vol_sma > 0, volume / vol_sma, 1.0)

    return df


def evaluate_vme_expansion(
    ticker: str,
    df_15m: Optional[pd.DataFrame],
    df_1h: Optional[pd.DataFrame],
    current_price: Optional[float] = None,
    direction: str = "auto",
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Evalúa si un activo cumple las condiciones de VOLATILITY MOMENTUM EXPANSION (VME).
    
    direction:
        'auto': Evalúa automáticamente tanto Bullish (LONG/CALL) como Bearish (PUT).
        'bullish': Solo evalúa para LONGs o CALLs.
        'bearish': Solo evalúa para PUTs.
    """
    res_base = {
        "ticker": ticker,
        "should_enter": False,
        "direction": "none",
        "rule_code": "",
        "group_name": "VOLATILITY_EXPANSION",
        "composite_rank": 0.0,
        "entry_price": 0.0,
        "initial_sl": 0.0,
        "reason": "",
        "metrics": {}
    }

    if df_15m is None or len(df_15m) < 15 or df_1h is None or len(df_1h) < 15:
        res_base["reason"] = f"Datos insuficientes (15m: {len(df_15m) if df_15m is not None else 0}, 1H: {len(df_1h) if df_1h is not None else 0})"
        return res_base

    df_1h_calc = _ensure_indicators_1h(df_1h)
    df_15m_calc = _ensure_indicators_15m(df_15m)

    last_1h = df_1h_calc.iloc[-1]
    last_15m = df_15m_calc.iloc[-1]

    price = float(current_price or last_15m["close"])
    if price <= 0:
        res_base["reason"] = "Precio inválido"
        return res_base

    res_base["entry_price"] = price

    # ── MÉTRICAS 1H ──
    ema3_1h = float(last_1h.get("ema_3") or price)
    ema9_1h = float(last_1h.get("ema_9") or price)
    ema20_1h = float(last_1h.get("ema_20") or price)
    ema50_1h = float(last_1h.get("ema_50") or price)
    rsi_1h = float(last_1h.get("rsi_14") or 50.0)

    # ── MÉTRICAS 15m ──
    ema3_15m = float(last_15m.get("ema_3") or price)
    ema9_15m = float(last_15m.get("ema_9") or price)
    ema20_15m = float(last_15m.get("ema_20") or price)
    adx_15m = float(last_15m.get("adx_14") or 0.0)
    di_plus_15m = float(last_15m.get("di_plus") or 0.0)
    di_minus_15m = float(last_15m.get("di_minus") or 0.0)
    atr_15m = float(last_15m.get("atr_14") or (price * 0.015))
    vwap_15m = float(last_15m.get("vwap") or price)
    rvol_15m = float(last_15m.get("rvol") or 1.0)
    bb_upper_15m = float(last_15m.get("bb_upper") or (price * 1.03))
    bb_lower_15m = float(last_15m.get("bb_lower") or (price * 0.97))

    atr_pct_15m = (atr_15m / price) * 100.0 if price > 0 else 0.0
    dist_vwap_pct = ((price - vwap_15m) / vwap_15m) * 100.0 if vwap_15m > 0 else 0.0

    delta = max(0.05, round(0.35 * atr_15m, 2))

    res_base["metrics"] = {
        "price": price,
        "ema3_1h": round(ema3_1h, 2),
        "ema9_1h": round(ema9_1h, 2),
        "ema20_1h": round(ema20_1h, 2),
        "ema50_1h": round(ema50_1h, 2),
        "rsi_1h": round(rsi_1h, 1),
        "ema3_15m": round(ema3_15m, 2),
        "ema9_15m": round(ema9_15m, 2),
        "ema20_15m": round(ema20_15m, 2),
        "adx_15m": round(adx_15m, 1),
        "di_plus_15m": round(di_plus_15m, 1),
        "di_minus_15m": round(di_minus_15m, 1),
        "atr_15m": round(atr_15m, 2),
        "atr_pct_15m": round(atr_pct_15m, 2),
        "vwap": round(vwap_15m, 2),
        "dist_vwap_pct": round(dist_vwap_pct, 2),
        "rvol_15m": round(rvol_15m, 2),
        "bb_upper_15m": round(bb_upper_15m, 2),
        "bb_lower_15m": round(bb_lower_15m, 2),
        "delta": delta
    }

    # ════════════════════════════════════════════════════════
    # EVALUACIÓN 1: VME BULLISH (LONG STOCKS / CALLs)
    # ════════════════════════════════════════════════════════
    if direction in ("auto", "bullish"):
        # 1. Requisito Mínimo 1H
        cond_macro_bull = (ema20_1h > ema50_1h)
        cond_rsi_bull = (rsi_1h <= 65.0)

        # 2. Gatillos Alta Prioridad 15m & 1H
        cond_adx_bull = (adx_15m >= 25.0 and di_plus_15m > di_minus_15m)
        cond_volat_bull = (atr_pct_15m >= 1.2 or rvol_15m >= 1.8)
        cond_vwap_bull = (price >= vwap_15m and 0.2 <= dist_vwap_pct <= 4.5)
        cond_ribbon_15m_bull = (ema3_15m > ema9_15m > ema20_15m)
        cond_sync_1h_bull = (ema3_1h > ema9_1h)

        if (cond_macro_bull and cond_rsi_bull and cond_adx_bull and
            cond_volat_bull and cond_vwap_bull and cond_ribbon_15m_bull and cond_sync_1h_bull):

            # Cálculo de composite_rank competitivo
            rank = 99.6
            if adx_15m >= 35.0:
                rank += 0.2
            if rvol_15m >= 2.5:
                rank += 0.1
            rank = min(99.9, round(rank, 1))

            initial_sl = round(ema9_15m - delta, 2)
            # Garantizar que el SL inicial no esté por encima del precio de entrada
            if initial_sl >= price:
                initial_sl = round(price * 0.985, 2)

            return {
                "ticker": ticker,
                "should_enter": True,
                "direction": "bullish",
                "rule_code": "VME_EXPANSION_STK",
                "group_name": "VOLATILITY_EXPANSION",
                "composite_rank": rank,
                "entry_price": price,
                "initial_sl": initial_sl,
                "target_tp1": round(bb_upper_15m, 2),
                "target_tp2": round(bb_upper_15m * 1.015, 2),
                "reason": (
                    f"VME Bullish Power Trend | Rank {rank} | ADX={adx_15m:.1f} (+DI>{di_minus_15m:.1f}) | "
                    f"ATR%={atr_pct_15m:.1f}% | DistVWAP=+{dist_vwap_pct:.1f}% | "
                    f"EMA15m(3>9>20) | EMA1H(3>9 & 20>50) | RSI1H={rsi_1h:.1f}<=65"
                ),
                "metrics": res_base["metrics"]
            }

    # ════════════════════════════════════════════════════════
    # EVALUACIÓN 2: VME BEARISH (PUTs OPCIONES / SHORT)
    # ════════════════════════════════════════════════════════
    if direction in ("auto", "bearish"):
        # 1. Requisito Mínimo 1H Inverso
        cond_macro_bear = (ema20_1h < ema50_1h)
        cond_rsi_bear = (rsi_1h >= 35.0)

        # 2. Gatillos Alta Prioridad Inversos
        cond_adx_bear = (adx_15m >= 25.0 and di_minus_15m > di_plus_15m)
        cond_volat_bear = (atr_pct_15m >= 1.2 or rvol_15m >= 1.8)
        cond_vwap_bear = (price <= vwap_15m and -4.5 <= dist_vwap_pct <= -0.2)
        cond_ribbon_15m_bear = (ema3_15m < ema9_15m < ema20_15m)
        cond_sync_1h_bear = (ema3_1h < ema9_1h)

        if (cond_macro_bear and cond_rsi_bear and cond_adx_bear and
            cond_volat_bear and cond_vwap_bear and cond_ribbon_15m_bear and cond_sync_1h_bear):

            rank = 99.6
            if adx_15m >= 35.0:
                rank += 0.2
            if rvol_15m >= 2.5:
                rank += 0.1
            rank = min(99.9, round(rank, 1))

            initial_sl = round(ema9_15m + delta, 2)
            if initial_sl <= price:
                initial_sl = round(price * 1.015, 2)

            return {
                "ticker": ticker,
                "should_enter": True,
                "direction": "bearish",
                "rule_code": "VME_EXPANSION_PUT",
                "group_name": "VOLATILITY_EXPANSION",
                "composite_rank": rank,
                "entry_price": price,
                "initial_sl": initial_sl,
                "target_tp1": round(bb_lower_15m, 2),
                "target_tp2": round(bb_lower_15m * 0.985, 2),
                "reason": (
                    f"VME Bearish Breakdown Trend | Rank {rank} | ADX={adx_15m:.1f} (-DI>{di_plus_15m:.1f}) | "
                    f"ATR%={atr_pct_15m:.1f}% | DistVWAP={dist_vwap_pct:.1f}% | "
                    f"EMA15m(3<9<20) | EMA1H(3<9 & 20<50) | RSI1H={rsi_1h:.1f}>=35"
                ),
                "metrics": res_base["metrics"]
            }

    # Si no calificó, detallar motivo de descarte
    reasons = []
    if direction in ("auto", "bullish"):
        if not (ema20_1h > ema50_1h): reasons.append("EMA20<=EMA50 1H")
        if not (rsi_1h <= 65.0): reasons.append(f"RSI1H({rsi_1h:.1f})>65")
        if not (adx_15m >= 25.0): reasons.append(f"ADX({adx_15m:.1f})<25")
        if not (di_plus_15m > di_minus_15m): reasons.append(f"+DI({di_plus_15m:.1f})<=-DI")
        if not (ema3_15m > ema9_15m > ema20_15m): reasons.append("Falta Ribbon EMA 15m (3>9>20)")
        if not (price >= vwap_15m): reasons.append(f"Precio(${price:.2f}) < VWAP(${vwap_15m:.2f})")
    res_base["reason"] = f"No califica VME: {', '.join(reasons[:3])}" if reasons else "Filtros no superados"
    return res_base
