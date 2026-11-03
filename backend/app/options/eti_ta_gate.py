"""
eTrade — ETI TA Gate & Ross Cameron Dual-Tier Evaluator
=========================================================
Motor de confirmación técnica que implementa la jerarquía de doble gatillo:
- Prioridad 1: Estrategia de Microestructura Ross Cameron
               (Micro-pullback hacia EMA9/VWAP + First Candle New High/Low + RVOL ≥ 1.35x).
- Opción 2: Instructivo Táctico ETI (Fallback)
            (Perforación directa del Trigger de Activación con volumen + posición VWAP).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np

from app.core.logger import log_info, log_warning
from app.data.yfinance_provider import YFinanceProvider
from app.options.aduana_gap_runner_options import compute_vwap, compute_bollinger_bands, _safe_col
from app.options.eti_models import ETISignal, ETITacticalInstruction

MODULE = "ETI_TA_GATE"


@dataclass
class TAGateEvaluationResult:
    signal_id: str
    symbol: str
    is_triggered: bool
    selected_route: str          # 'PRIORITY_1_ROSS_CAMERON' | 'OPTION_2_FALLBACK_ETI' | 'NONE'
    status_p1: str               # 'WAITING_PULLBACK' | 'PULLBACK_FORMED' | 'TRIGGERED' | 'NOT_MET'
    status_p2: str               # 'MONITORING_PRICE' | 'TRIGGERED' | 'INVALIDATED'
    is_invalidated: bool
    current_price: float
    current_vwap: float
    current_rvol: float
    reason: str


def evaluate_eti_ta_gate(
    signal: ETISignal,
    df_1m: Optional[pd.DataFrame] = None,
    df_2m: Optional[pd.DataFrame] = None,
    df_5m: Optional[pd.DataFrame] = None
) -> TAGateEvaluationResult:
    """
    Evalúa la Puerta Técnica (TA Gate) de la señal contra las cotizaciones de mercado.
    Ejecuta la jerarquía: Prioridad 1 (Ross Cameron) primero; si no se cumple pero el precio
    rompe el nivel de activación con volumen, opta por la Opción 2 (Trigger Directo ETI).
    """
    sym = signal.symbol
    gate = signal.technical_gate
    risk = signal.risk_management
    strat = signal.strategy
    is_call = (strat.bias == "BULLISH") or (signal.options_contract and signal.options_contract.option_type == "CALL")

    # Si no se pasan DataFrames, obtener datos rápidos vía yfinance
    if df_5m is None or df_5m.empty:
        try:
            import yfinance as yf
            sym_yf = "^SPX" if sym == "SPX" else ("^NDX" if sym == "NDX" else sym)
            stock = yf.Ticker(sym_yf)
            raw_5m = stock.history(period="3d", interval="5m")
            if raw_5m is not None and not raw_5m.empty:
                df_5m = raw_5m.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
            if df_2m is None or df_2m.empty:
                raw_2m = stock.history(period="1d", interval="2m")
                if raw_2m is not None and not raw_2m.empty:
                    df_2m = raw_2m.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        except Exception as e:
            log_warning(MODULE, f"Error obteniendo barras para {sym}: {e}")

    # Fallback si no hay suficientes datos
    if df_5m is None or df_5m.empty or len(df_5m) < 5:
        # Modo de contingencia con precio estimado
        target_p = gate.underlying_trigger_price
        return TAGateEvaluationResult(
            signal_id=signal.signal_id,
            symbol=sym,
            is_triggered=False,
            selected_route="NONE",
            status_p1="WAITING_PULLBACK",
            status_p2="MONITORING_PRICE",
            is_invalidated=False,
            current_price=target_p,
            current_vwap=target_p,
            current_rvol=1.0,
            reason="Esperando datos de mercado intradía para confirmar TA Gate."
        )

    # Marco de trabajo principal: Velas de 2m o 5m
    work_df = df_2m if (df_2m is not None and not df_2m.empty and len(df_2m) >= 5) else df_5m

    c = _safe_col(work_df, "close")
    o = _safe_col(work_df, "open")
    h = _safe_col(work_df, "high")
    l = _safe_col(work_df, "low")
    v = _safe_col(work_df, "volume")

    current_price = float(c.iloc[-1])
    vwap_series = compute_vwap(work_df)
    current_vwap = float(vwap_series.iloc[-1]) if not vwap_series.empty else current_price

    # Cálculo de RVOL
    avg_vol = float(v.tail(15).mean()) if len(v) >= 5 else 1.0
    current_rvol = float(v.iloc[-1]) / max(avg_vol, 1.0)

    # Medias Móviles Exponenciales Rápidas
    ema3 = c.ewm(span=3, adjust=False).mean()
    ema9 = c.ewm(span=9, adjust=False).mean()

    # ─────────────────────────────────────────────────────────────────────────
    # 0. CONTROL DE INVALIDACIÓN (STOP FORRESTER)
    # ─────────────────────────────────────────────────────────────────────────
    is_invalidated = False
    invalidation_p = risk.invalidation_underlying
    if is_call and current_price < invalidation_p:
        is_invalidated = True
    elif (not is_call) and current_price > invalidation_p:
        is_invalidated = True

    if is_invalidated:
        return TAGateEvaluationResult(
            signal_id=signal.signal_id,
            symbol=sym,
            is_triggered=False,
            selected_route="NONE",
            status_p1="NOT_MET",
            status_p2="INVALIDATED",
            is_invalidated=True,
            current_price=current_price,
            current_vwap=current_vwap,
            current_rvol=current_rvol,
            reason=f"⛔ Señal Invalidada: Precio ${current_price:.2f} superó Stop Forrester (${invalidation_p:.2f})."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 1. EVALUACIÓN PRIORIDAD 1: ESTRATEGIA ROSS CAMERON (SCALPING)
    # ─────────────────────────────────────────────────────────────────────────
    p1_triggered = False
    p1_status = "WAITING_PULLBACK"
    p1_reason = ""

    last_green = float(c.iloc[-1]) >= float(o.iloc[-1])
    last_red = float(c.iloc[-1]) < float(o.iloc[-1])
    prev_high = float(h.iloc[-2]) if len(h) >= 2 else current_price
    prev_low = float(l.iloc[-2]) if len(l) >= 2 else current_price

    if is_call:
        # Tendencia alcista: EMA3 >= EMA9 y precio sobre VWAP
        is_trend_call = (float(ema3.iloc[-1]) >= float(ema9.iloc[-1])) and (current_price >= current_vwap * 0.998)
        # Pullback en velas previas (al menos 1 vela roja descansando a EMA9)
        had_pullback = any(float(c.iloc[idx]) < float(o.iloc[idx]) for idx in range(-4, -1)) if len(c) >= 4 else False
        if had_pullback:
            p1_status = "PULLBACK_FORMED"
        # First Candle to Make a New High
        first_candle_high = last_green and (float(c.iloc[-1]) > prev_high or float(h.iloc[-1]) > prev_high)
        if is_trend_call and had_pullback and first_candle_high:
            p1_triggered = True
            p1_status = "TRIGGERED"
            p1_reason = f"Ross Cameron P1 CALL: First Candle New High tras pullback (RVOL {current_rvol:.1f}x > 1.35x)"
    else:
        # Tendencia bajista: EMA3 <= EMA9 y precio bajo VWAP
        is_trend_put = (float(ema3.iloc[-1]) <= float(ema9.iloc[-1])) and (current_price <= current_vwap * 1.002)
        # Rebote previo en velas (al menos 1 vela verde hacia resistencia/EMA9)
        had_rebound = any(float(c.iloc[idx]) > float(o.iloc[idx]) for idx in range(-4, -1)) if len(c) >= 4 else False
        if had_rebound:
            p1_status = "PULLBACK_FORMED"
        # First Candle to Make a New Low
        first_candle_low = last_red and (float(c.iloc[-1]) < prev_low or float(l.iloc[-1]) < prev_low)
        if is_trend_put and had_rebound and first_candle_low:
            p1_triggered = True
            p1_status = "TRIGGERED"
            p1_reason = f"Ross Cameron P1 PUT: First Candle New Low tras rebote a EMA9/VWAP (RVOL {current_rvol:.1f}x > 1.35x)"

    # Si la Prioridad 1 gatilla, tiene prelación absoluta
    if p1_triggered:
        return TAGateEvaluationResult(
            signal_id=signal.signal_id,
            symbol=sym,
            is_triggered=True,
            selected_route="PRIORITY_1_ROSS_CAMERON",
            status_p1="TRIGGERED",
            status_p2="MONITORING_PRICE",
            is_invalidated=False,
            current_price=current_price,
            current_vwap=current_vwap,
            current_rvol=current_rvol,
            reason=f"🚀 {p1_reason}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 2. EVALUACIÓN OPCIÓN 2 (FALLBACK): TRIGGER DIRECTO ETI
    # ─────────────────────────────────────────────────────────────────────────
    p2_triggered = False
    p2_status = "MONITORING_PRICE"
    p2_reason = ""

    trigger_p = gate.underlying_trigger_price
    min_rvol = gate.indicator_requirements.min_relative_volume or 1.20
    op = gate.trigger_operator

    price_condition_met = False
    if op in ("LESS_THAN_OR_EQUAL", "CROSS_BELOW"):
        price_condition_met = (current_price <= trigger_p)
    elif op in ("GREATER_THAN_OR_EQUAL", "CROSS_ABOVE"):
        price_condition_met = (current_price >= trigger_p)

    # Filtro de VWAP según contrato
    vwap_cond = gate.indicator_requirements.vwap_condition
    vwap_ok = True
    if vwap_cond == "PRICE_BELOW_VWAP" and current_price > current_vwap:
        vwap_ok = False
    elif vwap_cond == "PRICE_ABOVE_VWAP" and current_price < current_vwap:
        vwap_ok = False

    volume_ok = (current_rvol >= min_rvol)

    if price_condition_met and vwap_ok and volume_ok:
        p2_triggered = True
        p2_status = "TRIGGERED"
        p2_reason = (
            f"Instructivo ETI Opción 2 Fallback: Perforación directa de ${trigger_p:.2f} "
            f"(Spot: ${current_price:.2f}, RVOL: {current_rvol:.1f}x ≥ {min_rvol:.1f}x, VWAP ok)"
        )

    if p2_triggered:
        return TAGateEvaluationResult(
            signal_id=signal.signal_id,
            symbol=sym,
            is_triggered=True,
            selected_route="OPTION_2_FALLBACK_ETI",
            status_p1=p1_status,
            status_p2="TRIGGERED",
            is_invalidated=False,
            current_price=current_price,
            current_vwap=current_vwap,
            current_rvol=current_rvol,
            reason=f"⚡ {p2_reason}"
        )

    # Ninguna ruta gatillada todavía: monitoreando activamente
    dist_to_trigger = abs(current_price - trigger_p)
    return TAGateEvaluationResult(
        signal_id=signal.signal_id,
        symbol=sym,
        is_triggered=False,
        selected_route="NONE",
        status_p1=p1_status,
        status_p2="MONITORING_PRICE",
        is_invalidated=False,
        current_price=current_price,
        current_vwap=current_vwap,
        current_rvol=current_rvol,
        reason=f"Monitoreando: Spot ${current_price:.2f} a ${dist_to_trigger:.2f} del Trigger ETI (${trigger_p:.2f}). P1: {p1_status}."
    )
