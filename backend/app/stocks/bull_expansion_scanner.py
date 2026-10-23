"""
eTrade v7.0 — BULL TREND EXPANSION INTRADAY IGNITION SCANNER
=============================================================
Motor recurrente de alta frecuencia para detectar acciones institucionales sólidas
en régimen BULL_TREND_EXPANSION (EMA 3 > 9 > 20 > 50 > 200 en gráfico diario) que
acaban de encender su nuevo tramo de impulso intradía marcando High > High_prev en 15m.

Características:
1. Filtro Secular 1D: STRUCTURAL_REGIME == BULL_TREND_EXPANSION con espacio a BB Upper.
2. Gatillo Táctico 15m: Vela marcando nuevo máximo (High[t] > High[t-1]), sobre VWAP y sobre Open del día.
3. Catalizador Opcional de Reafirmación (+20 pts):
   - No excluyente: si no tiene noticia, califica por inercia técnica (+10 pts).
   - Si tiene noticia Tier 1/2 (<48h), recibe +20 pts y convicción MAXIMUM.
4. Doble Salida: Candidato para Stocks Spot (Swing/Intraday) y Opciones (Bull Call Spreads / Calls).
"""

from __future__ import annotations
import time
from typing import Dict, Any, Optional, List

from app.core.logger import log_info, log_warning, log_debug
from app.core.structural_regime_engine import evaluate_structural_regime
from app.stocks.live_1h_candle_service import get_live_1h_candle_and_sipv
from app.stocks.catalyst_classifier import analyze_ticker_live_catalyst

MODULE = "BULL_EXPANSION_SCANNER"


def scan_single_ticker_bull_expansion(
    ticker: str,
    current_price: Optional[float] = None,
    news_items: Optional[list] = None
) -> Optional[Dict[str, Any]]:
    """
    Evalúa si un ticker individual califica bajo el setup BULL_TREND_EXPANSION IGNITION.
    Retorna el diccionario estructurado del candidato o None si no califica.
    """
    clean_ticker = str(ticker).replace("/", "").replace(".", "").upper().strip()
    if not clean_ticker:
        return None

    try:
        # ── 1. EVALUACIÓN ESTRUCTURAL 1D (Filtro Secular) ──
        regime_info = evaluate_structural_regime(clean_ticker, current_price or 0.0)
        regime_code = regime_info.get("regime_code", "UNKNOWN")
        
        # Debe estar en BULL_TREND_EXPANSION estricto
        if regime_code != "BULL_TREND_EXPANSION":
            return None

        price = current_price or float(regime_info.get("current_price") or regime_info.get("ema3") or 10.0)
        room_to_bb = float(regime_info.get("room_to_bb_upper_pct") or 0.0)
        if room_to_bb < 2.5:
            # Muy pegado al techo de Bollinger Diario, poco recorrido
            return None

        # ── 2. GATILLO INTRADÍA 15m & SALUD DEL PRECIO ──
        live_1h = get_live_1h_candle_and_sipv(clean_ticker, price)
        
        # a) High > High vela anterior (Vela creciente en 15m)
        is_15m_growing = bool(live_1h.get("is_15m_high_growing", False))
        if not is_15m_growing:
            return None

        # b) Precio cotizando sobre VWAP y sobre Open del día
        vwap = float(live_1h.get("vwap_intraday", 0.0))
        day_open = float(live_intraday_open := live_1h.get("day_open_price", 0.0))
        if vwap > 0 and price < vwap * 0.998:
            return None
        if day_open > 0 and price < day_open * 0.998:
            return None

        # c) Anti-Rechazo: No mecha superior destructiva
        upper_wick = float(live_1h.get("upper_wick_ratio", 0.0))
        if upper_wick >= 0.38:
            return None

        # d) Bandas Bollinger en 15m
        is_15m_bb_break = bool(live_1h.get("is_15m_bb_breakout", False))
        is_bb_15m_opening = bool(live_1h.get("is_bb_15m_opening", False))

        # ── 3. EVALUACIÓN DE CATALIZADOR (OPCIONAL PERO REAFIRMANTE) ──
        cat_info = analyze_ticker_live_catalyst(clean_ticker, news_items)
        tier = cat_info.get("tier", 3)
        has_catalyst = (tier in (1, 2) and not cat_info.get("is_toxic", False))

        if has_catalyst:
            conviction = "MAXIMUM"
            score_bonus = 20.0
            label = f"🟢 BULL EXPANSION + CATALYST ({cat_info.get('catalyst_name', 'Noticia')})"
            tip = (
                f"Ignición alcista confirmada con catalizador {cat_info.get('catalyst_name')}: "
                f"Vela 15m marcando nuevo máximo (${price:.2f}) en tendencia secular diaria (EMA 3>9>20>50>200). "
                f"Máxima convicción con camino libre a Bollinger Superior (+{room_to_bb:.1f}%)."
            )
            rule_code = "STE_BULL_EXPANSION_CATALYST"
        else:
            conviction = "HIGH"
            score_bonus = 10.0
            label = "🟢 BULL EXPANSION IGNITION (High > Prev High)"
            tip = (
                f"Ignición técnica en tendencia alcista secular: Vela 15m marcando nuevo máximo (${price:.2f}) "
                f"sobre VWAP (${vwap:.2f}) en modo BULL_TREND_EXPANSION. Vía libre hacia BB Superior (+{room_to_bb:.1f}%)."
            )
            rule_code = "STE_BULL_EXPANSION_IGNITION"

        # Ranking score (90 a 99)
        base_score = 80.0
        bonus_opening = 5.0 if is_bb_15m_opening else 0.0
        bonus_break = 3.0 if is_15m_bb_break else 0.0
        rank_score = round(min(99.0, max(90.0, base_score + score_bonus + bonus_opening + bonus_break)), 1)

        candidate = {
            "ticker": clean_ticker,
            "price": round(price, 2),
            "price_at_rank": round(price, 2),
            "composite_rank": rank_score,
            "rank_score": rank_score,
            "confidence": conviction.lower(),
            "conviction": conviction,
            "group_name": "STRUCTURAL_EXPANSION",
            "triggered_rule": rule_code,
            "entry_reason": f"{rule_code}: High 15m creciente en BULL_TREND_EXPANSION (+{room_to_bb:.1f}% a BB 1D)",
            "semaphore": "BULL_EXPANSION_IGNITION",
            "semaphore_label": label,
            "semaphore_color": "#10B981",
            "semaphore_tip": tip,
            "rule_code": rule_code,
            "has_news": has_catalyst,
            "catalyst_tier": tier,
            "catalyst_name": cat_info.get("catalyst_name", ""),
            "catalyst_headline": cat_info.get("headline", ""),
            "room_to_bb_upper_1d": room_to_bb,
            "tactical_target_ceiling": float(regime_info.get("bb_upper") or (price * 1.08)),
            "is_bull_expansion": True,
            "is_15m_high_growing": is_15m_growing,
            "is_15m_bb_breakout": is_15m_bb_break,
            "is_bb_15m_opening": is_bb_15m_opening,
            "vwap_intraday": round(vwap, 3),
            "day_open_price": round(day_open, 2),
            "vol_decay_ratio_15m": float(live_1h.get("vol_decay_ratio_15m", 1.0)),
            # Datos para despacho de Opciones
            "recommended_option_strategy": "bull_call_spread",
            "suggested_option_dte": "14-21d",
            "target_wall_ema9": float(regime_info.get("ema9") or (price * 0.98)),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        log_info(MODULE, f"🎯 CANDIDATO CALIFICADO: {clean_ticker} @ ${price:.2f} | Rank={rank_score} | {conviction} | {label}")
        return candidate

    except Exception as e:
        log_warning(MODULE, f"Error evaluando Bull Expansion para {clean_ticker}: {e}")
        return None


def scan_universe_bull_expansion(
    tickers: List[str],
    max_candidates: int = 10
) -> List[Dict[str, Any]]:
    """
    Escanea una lista de tickers y retorna los calificados ordenados por rank_score descendente.
    """
    results = []
    unique_tickers = list(dict.fromkeys([str(t).upper().strip() for t in tickers if t]))
    
    log_debug(MODULE, f"Iniciando escaneo de Bull Expansion Ignition para {len(unique_tickers)} tickers...")
    
    for t in unique_tickers:
        cand = scan_single_ticker_bull_expansion(t)
        if cand:
            results.append(cand)
            if len(results) >= max_candidates * 2:
                break

    # Ordenar por mayor rank score
    results.sort(key=lambda x: x.get("composite_rank", 0.0), reverse=True)
    return results[:max_candidates]
