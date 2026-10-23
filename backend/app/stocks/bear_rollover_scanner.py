"""
eTrade v7.0 — BEAR ROLLOVER INTRADAY PUT SCANNER
=================================================
Motor recurrente para la detección de configuraciones bajistas de alta probabilidad
en opciones PUT (Bear Put Spreads / Long Puts).

Principio Clave:
A diferencia del lado alcista, las caídas son rápidas y violentas ("por ascensor").
Esperar una alineación rígida en 1D (EMA3 < 9 < 20 < 50 < 200) hace llegar tarde,
cuando el precio ya colapsó contra la Banda Inferior de Bollinger con IV inflada.

Este motor busca el "Bearish Rollover" óptimo:
1. Estructura de Fondo 1D: EMA9 < EMA20 < EMA50 o quiebre de soporte mayor (EMA20/EMA50).
2. Ubicación en Resistencia: El activo rebotó hacia EMA9 o EMA20 (precio arriba, no en el suelo).
3. Margen Amplio de Caída: Margen hasta Bollinger Inferior 1D >= 4.5% (prohibido comprar en sobreventa).
4. Gatillo Intradía 15m: Quiebre de mínimos (Low[t] < Low[t-1]), cotizando bajo VWAP y bajo Open del día,
   sin absorción compradora (Lower Wick < 0.35).
5. Catalizador Bajista Opcional (+20 pts):
   - Si tiene noticia negativa Tier 1 (Earnings miss, Guidance cut, Dilución, FDA CRL): Convicción MAXIMUM.
   - Si no tiene noticia: Califica por inercia técnica (+10 pts, Convicción HIGH).
"""

from __future__ import annotations
import time
from typing import Dict, Any, Optional, List

from app.core.logger import log_info, log_warning, log_debug
from app.core.structural_regime_engine import fetch_daily_metrics
from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
from app.stocks.catalyst_classifier import analyze_ticker_live_bearish_catalyst

MODULE = "BEAR_ROLLOVER_SCANNER"


def scan_single_ticker_bear_rollover(
    ticker: str,
    current_price: Optional[float] = None,
    news_items: Optional[list] = None
) -> Optional[Dict[str, Any]]:
    """
    Evalúa si un ticker califica bajo el setup BEAR_ROLLOVER para PUTs de opciones.
    Retorna el diccionario estructurado del candidato o None si no califica.
    """
    clean_ticker = str(ticker).replace("/", "").replace(".", "").upper().strip()
    if not clean_ticker:
        return None

    try:
        # ── 1. EVALUACIÓN ESTRUCTURAL 1D & DISTANCIAS ──
        metrics = fetch_daily_metrics(clean_ticker, current_price or 0.0)
        price = current_price or float(metrics.get("ema3") or 10.0)

        ema9 = float(metrics.get("ema9") or price)
        ema20 = float(metrics.get("ema20") or price)
        ema50 = float(metrics.get("ema50") or price)
        ema200 = float(metrics.get("ema200") or price)
        bb_lower = float(metrics.get("bb_lower") or (price * 0.85))
        bb_upper = float(metrics.get("bb_upper") or (price * 1.15))
        bb_bandwidth = float(metrics.get("bb_bandwidth_pct") or 20.0)

        # a) Fondo Bajista Macro o Quiebre Estructural Mayor
        is_macro_bear = (ema9 < ema20) and (ema20 < ema50 or price < ema200 or ema50 < ema200)
        is_breakdown = (price < ema20 and price < ema50)

        if not is_macro_bear and not is_breakdown:
            # Estructura alcista intacta, no califica para PUTs
            return None

        # b) Margen de Caída a Bollinger Inferior (Filtro Anti-Sobreventa)
        room_to_bb_lower_pct = round(((price - bb_lower) / price * 100.0), 2) if price > 0 else 0.0
        if room_to_bb_lower_pct < 4.5:
            # Ya está en el suelo de Bollinger 1D. Riesgo extremo de IV crush y rebote técnico.
            return None

        # c) Ubicación en Resistencia (No sobreextendido a la baja)
        # Si el precio cotiza > 8% por debajo de la EMA9 diaria, está descolgado (over-extended)
        if price < ema9 * 0.92:
            return None
        # Si el precio cotiza > 2.5% por encima de la EMA20 diaria, ha quebrado al alza
        if price > ema20 * 1.025:
            return None

        # ── 2. GATILLO INTRADÍA 15m & SALUD DEL PRECIO ──
        live_1h = get_live_1h_candle_and_sipv(clean_ticker, price)

        # a) No debe estar haciendo nuevos máximos en 15m
        is_15m_high_growing = bool(live_1h.get("is_15m_high_growing", False))
        if is_15m_high_growing:
            return None

        # b) Quiebre de mínimos en 15m o vela roja en 1H
        is_15m_low_breaking = bool(live_1h.get("is_15m_low_breaking", False))
        is_red_1h = bool(live_1h.get("is_red_candle_1h", True))
        if not is_15m_low_breaking and not is_red_1h:
            return None

        # c) Cotización por debajo de VWAP y por debajo del Open del día (vela intradía roja)
        vwap = float(live_1h.get("vwap_intraday", 0.0))
        day_open = float(live_1h.get("day_open_price", 0.0))
        if vwap > 0 and price > vwap * 1.002:
            # Trampa de osos: el precio recuperó el VWAP intradía
            return None
        if day_open > 0 and price > day_open * 1.002:
            # Vela verde intradía sobre el Open
            return None

        # d) Anti-Absorción Compradora (Sin mechas inferiores largas)
        lower_wick = float(live_1h.get("lower_wick_ratio", 0.0))
        if lower_wick >= 0.35:
            # Rechazo de mínimos (compras absorbiendo la caída)
            return None

        # e) Bollinger 15m
        is_15m_bb_lower = bool(live_1h.get("is_15m_bb_breakdown_lower", False))
        is_bb_15m_opening = bool(live_1h.get("is_bb_15m_opening", False))

        # ── 3. EVALUACIÓN DE CATALIZADOR BAJISTA (OPCIONAL PERO REAFIRMANTE) ──
        cat_info = analyze_ticker_live_bearish_catalyst(clean_ticker, news_items)
        has_catalyst = bool(cat_info.get("is_bearish", False))

        if has_catalyst:
            conviction = "MAXIMUM"
            score_bonus = 20.0
            label = f"🔴 BEAR ROLLOVER + CATALYST ({cat_info.get('catalyst_name', 'Noticia')})"
            tip = (
                f"Quiebre bajista de alta convicción confirmado con catalizador {cat_info.get('catalyst_name')}: "
                f"Rechazo en resistencia (EMA9/EMA20) y vela 15m marcando nuevo mínimo (${price:.2f}) bajo VWAP (${vwap:.2f}). "
                f"Margen libre de caída hacia Bollinger Inferior (-{room_to_bb_lower_pct:.1f}%)."
            )
            rule_code = "OPT_BEAR_ROLLOVER_CATALYST"
        else:
            conviction = "HIGH"
            score_bonus = 10.0
            label = "🔴 BEAR ROLLOVER IGNITION (Rechazo en Resistencia + Low < Prev Low)"
            tip = (
                f"Rollover bajista técnico: Rechazo en resistencia EMA9/EMA20 diaria con quiebre de mínimo en 15m (${price:.2f}) "
                f"bajo VWAP (${vwap:.2f}). Margen amplio de caída hacia BB Inferior (-{room_to_bb_lower_pct:.1f}%)."
            )
            rule_code = "OPT_BEAR_ROLLOVER_IGNITION"

        # Ranking score (90 a 99)
        base_score = 80.0
        bonus_opening = 5.0 if is_bb_15m_opening else 0.0
        bonus_break = 3.0 if is_15m_bb_lower else 0.0
        rank_score = round(min(99.0, max(90.0, base_score + score_bonus + bonus_opening + bonus_break)), 1)

        # ── 4. ESTRUCTURACIÓN DE ESTRATEGIA DE OPCIONES ──
        # Si las bandas diarias están muy abiertas o hay catalizador, la IV es alta -> Bear Put Spread para neutralizar Vega.
        # Si la volatilidad es moderada -> Long Put direccional o Bear Put Spread.
        recommended_strategy = "bear_put_spread" if (bb_bandwidth > 25.0 or has_catalyst) else "long_put"

        candidate = {
            "ticker": clean_ticker,
            "price": round(price, 2),
            "price_at_rank": round(price, 2),
            "composite_rank": rank_score,
            "rank_score": rank_score,
            "confidence": conviction.lower(),
            "conviction": conviction,
            "direction": "bearish",
            "group_name": "BEAR_ROLLOVER_PUTS",
            "triggered_rule": rule_code,
            "entry_reason": f"{rule_code}: Rechazo en resistencia EMA9/EMA20 con -{room_to_bb_lower_pct:.1f}% margen a BB Lower",
            "semaphore": "BEAR_ROLLOVER_IGNITION",
            "semaphore_label": label,
            "semaphore_color": "#EF4444",
            "semaphore_tip": tip,
            "rule_code": rule_code,
            "has_news": has_catalyst,
            "catalyst_tier": cat_info.get("tier", 3),
            "catalyst_name": cat_info.get("catalyst_name", ""),
            "catalyst_headline": cat_info.get("headline", ""),
            "room_to_bb_lower_1d": room_to_bb_lower_pct,
            "tactical_target_floor": round(bb_lower, 2),
            "is_bear_rollover": True,
            "is_15m_low_breaking": is_15m_low_breaking,
            "is_15m_bb_breakdown_lower": is_15m_bb_lower,
            "is_bb_15m_opening": is_bb_15m_opening,
            "vwap_intraday": round(vwap, 3),
            "day_open_price": round(day_open, 2),
            # Especificaciones para Despacho de Opciones PUT
            "recommended_option_strategy": recommended_strategy,
            "suggested_option_dte": "14-28d",
            "target_delta": "-0.45 a -0.55",
            "resistance_wall_ema9": round(ema9, 2),
            "stop_loss_trigger": f"Cierre de vela 15m > ${min(ema9, vwap):.2f} (EMA9/VWAP)",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        log_info(MODULE, f"🎯 CANDIDATO PUT CALIFICADO: {clean_ticker} @ ${price:.2f} | Rank={rank_score} | {conviction} | {label}")
        return candidate

    except Exception as e:
        log_warning(MODULE, f"Error evaluando Bear Rollover para {clean_ticker}: {e}")
        return None


def scan_universe_bear_rollover(
    tickers: List[str],
    max_candidates: int = 5
) -> List[Dict[str, Any]]:
    """
    Escanea un universo de tickers buscando oportunidades de PUTs bajo Bear Rollover.
    Retorna la lista ordenada por composite_rank descendente.
    """
    candidates = []
    for ticker in tickers:
        cand = scan_single_ticker_bear_rollover(ticker)
        if cand:
            candidates.append(cand)

    candidates.sort(key=lambda x: x.get("composite_rank", 0.0), reverse=True)
    return candidates[:max_candidates]
