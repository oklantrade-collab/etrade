"""
eTrade v7.0 — MACRO SENTIMENT ENGINE (Universal Market Climate & Risk-Off Shield)
==================================================================================
Monitorea en tiempo real los 3 barómetros institucionales:
1. SPY (S&P 500) — Marea directiva general del mercado.
2. QQQ (Nasdaq 100) — Apetito por riesgo y beta tecnológico.
3. ^VIX (CBOE Volatility Index) — Termómetro del miedo y velocidad de pánico.

Regímenes Macro:
- 🟢 RISK_ON: SPY >= 0, QQQ >= 0, VIX < 18. Compras Long y Calls autorizadas.
- 🟡 NEUTRAL: Choppy / Mixto. Compras selectivas solo con Fuerza Relativa (RS > +1%).
- 🔴 RISK_OFF: SPY < -0.5% o QQQ < -1.0% o VIX Spike > +6%. Candado defensivo total para Stocks
               (prohibido comprar Longs); polaridad invertida en Opciones (prioridad Puts / Bear Spreads).
"""

from __future__ import annotations
import time
from typing import Dict, Any, Optional
import pandas as pd
from app.core.logger import log_info, log_warning, log_debug

MODULE = "MACRO_SENTIMENT"

# Caché en memoria: (timestamp, data_dict)
_MACRO_CACHE: tuple[float, Dict[str, Any]] | None = None
CACHE_TTL_SECONDS = 120.0  # 2 minutos


def fetch_macro_indicators() -> Dict[str, Any]:
    """Obtiene cotizaciones y variaciones del día para SPY, QQQ y ^VIX con caché en memoria."""
    global _MACRO_CACHE
    now = time.time()
    if _MACRO_CACHE is not None and (now - _MACRO_CACHE[0] < CACHE_TTL_SECONDS):
        return _MACRO_CACHE[1]

    data = {
        "spy": {"price": 0.0, "change_pct": 0.0, "prev_close": 0.0},
        "qqq": {"price": 0.0, "change_pct": 0.0, "prev_close": 0.0},
        "vix": {"level": 15.0, "change_pct": 0.0, "prev_close": 15.0},
        "updated_at": now
    }

    try:
        import yfinance as yf
        tickers = yf.Tickers("SPY QQQ ^VIX")
        
        # SPY
        try:
            h_spy = tickers.tickers["SPY"].history(period="2d")
            if len(h_spy) >= 2:
                p_prev = float(h_spy["Close"].iloc[-2])
                p_curr = float(h_spy["Close"].iloc[-1])
                data["spy"]["price"] = round(p_curr, 2)
                data["spy"]["prev_close"] = round(p_prev, 2)
                data["spy"]["change_pct"] = round(((p_curr - p_prev) / p_prev) * 100.0, 2)
        except Exception as e:
            log_warning(MODULE, f"Error obteniendo SPY: {e}")

        # QQQ
        try:
            h_qqq = tickers.tickers["QQQ"].history(period="2d")
            if len(h_qqq) >= 2:
                p_prev = float(h_qqq["Close"].iloc[-2])
                p_curr = float(h_qqq["Close"].iloc[-1])
                data["qqq"]["price"] = round(p_curr, 2)
                data["qqq"]["prev_close"] = round(p_prev, 2)
                data["qqq"]["change_pct"] = round(((p_curr - p_prev) / p_prev) * 100.0, 2)
        except Exception as e:
            log_warning(MODULE, f"Error obteniendo QQQ: {e}")

        # ^VIX
        try:
            h_vix = tickers.tickers["^VIX"].history(period="2d")
            if len(h_vix) >= 2:
                p_prev = float(h_vix["Close"].iloc[-2])
                p_curr = float(h_vix["Close"].iloc[-1])
                data["vix"]["level"] = round(p_curr, 2)
                data["vix"]["prev_close"] = round(p_prev, 2)
                data["vix"]["change_pct"] = round(((p_curr - p_prev) / p_prev) * 100.0, 2)
        except Exception as e:
            log_warning(MODULE, f"Error obteniendo VIX: {e}")

    except Exception as ge:
        log_warning(MODULE, f"Error global descargando macro: {ge}")

    _MACRO_CACHE = (now, data)
    return data


def evaluate_macro_sentiment() -> Dict[str, Any]:
    """
    Evalúa el estado del mercado y determina directivas para Stocks y Opciones.
    
    Returns dict:
      regime: 'RISK_ON' | 'NEUTRAL' | 'RISK_OFF'
      label: Texto formateado con emoji para badges
      allow_stock_buys: bool
      allow_option_calls: bool
      allow_option_puts: bool
      vix_level: float
      spy_change_pct: float
      qqq_change_pct: float
      vix_change_pct: float
      risk_factors: list[str]
      action_note: str
    """
    m = fetch_macro_indicators()
    spy_chg = m["spy"]["change_pct"]
    qqq_chg = m["qqq"]["change_pct"]
    vix_lvl = m["vix"]["level"]
    vix_chg = m["vix"]["change_pct"]

    risk_factors = []
    if spy_chg < -0.5:
        risk_factors.append(f"SPY en caída ({spy_chg:+.2f}%)")
    if qqq_chg < -1.0:
        risk_factors.append(f"QQQ con sangría tech ({qqq_chg:+.2f}%)")
    if vix_lvl >= 22.0:
        risk_factors.append(f"VIX elevado ({vix_lvl:.1f})")
    if vix_chg >= 6.0:
        risk_factors.append(f"Disparo de VIX (+{vix_chg:.1f}%)")

    # Determinación de Régimen
    is_risk_off = (
        spy_chg < -0.50 or
        qqq_chg < -1.00 or
        vix_chg >= 6.00 or
        vix_lvl >= 24.00
    )

    is_risk_on = (
        spy_chg >= 0.0 and
        qqq_chg >= 0.0 and
        vix_lvl < 18.0 and
        vix_chg < 2.0
    )

    if is_risk_off:
        regime = "RISK_OFF"
        label = f"🔴 RISK-OFF (SPY {spy_chg:+.1f}%, QQQ {qqq_chg:+.1f}%, VIX {vix_chg:+.1f}%)"
        allow_stock_buys = False
        allow_option_calls = False
        allow_option_puts = True
        action_note = (
            "Mercado institucional en liquidación / aversión al riesgo. "
            "Candado activo: Prohibido comprar acciones Long y Calls. Foco exclusivo en Puts / Bear Spreads."
        )
    elif is_risk_on:
        regime = "RISK_ON"
        label = f"🟢 RISK-ON (SPY {spy_chg:+.1f}%, VIX {vix_lvl:.1f})"
        allow_stock_buys = True
        allow_option_calls = True
        allow_option_puts = False
        action_note = (
            "Marea alcista favorable. Ambiente institucional óptimo para compras Long y Bull Call Spreads."
        )
    else:
        regime = "NEUTRAL"
        label = f"🟡 NEUTRAL / SELECTIVO (SPY {spy_chg:+.1f}%, VIX {vix_lvl:.1f})"
        allow_stock_buys = True  # Requiere filtro de Fuerza Relativa (RS > +1%)
        allow_option_calls = True
        allow_option_puts = True
        action_note = (
            "Mercado mixto o en rango. Operaciones permitidas solo en activos con Fuerza Relativa demostrada."
        )

    return {
        "regime": regime,
        "label": label,
        "allow_stock_buys": allow_stock_buys,
        "allow_option_calls": allow_option_calls,
        "allow_option_puts": allow_option_puts,
        "spy_price": m["spy"]["price"],
        "spy_change_pct": spy_chg,
        "qqq_price": m["qqq"]["price"],
        "qqq_change_pct": qqq_chg,
        "vix_level": vix_lvl,
        "vix_change_pct": vix_chg,
        "risk_factors": risk_factors,
        "action_note": action_note,
        "timestamp": time.time()
    }


def is_macro_risk_off() -> bool:
    """Devuelve True si el mercado está en Risk-Off y las compras deben bloquearse."""
    res = evaluate_macro_sentiment()
    return res["regime"] == "RISK_OFF"
