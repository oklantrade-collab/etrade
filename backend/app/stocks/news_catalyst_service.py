"""
eTrade Stocks — News Catalyst Service & Classifier
===================================================
Identifica catalizadores de noticias de hoy y ayer para las acciones del universo eTrade.
Clasifica los eventos en Tiers con bonificaciones cuantitativas al Ranking Score.
"""

import time
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import yfinance as yf
from app.core.logger import log_info, log_warning

MODULE = "NEWS_CATALYST_SERVICE"

# Cache en memoria: { ticker: { 'timestamp': float, 'data': dict } }
_NEWS_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 900  # 15 minutos


# Patrones de palabras clave para clasificación de catalizadores
TIER_1_PATTERNS = [
    (r"\b(fda|approval|approved|cleared|clearance|phase 3|clinical trial|kras|biotech)\b", "FDA / Aprobación", "tier_1", 25),
    (r"\b(patent|lawsuit|settlement|ended.*war|wins? dispute|court|ruling)\b", "Patente / Legal", "tier_1", 25),
    (r"\b(acquired|acquisition|merger|buyout|takeover|bid)\b", "Adquisición / M&A", "tier_1", 25),
    (r"\b(contract|awarded|pentagon|defense deal|government contract)\b", "Contrato Mayor", "tier_1", 25),
    (r"\b(oil exploration|arctic|drill|drilling|discovery)\b", "Recursos / Hallazgo", "tier_1", 25),
]

TIER_2_PATTERNS = [
    (r"\b(earnings|quarterly|q1|q2|q3|q4|revenue beat|eps beat|beats? estimates?|guidance raised|profit jumps?)\b", "Earnings / Resultados", "tier_2", 15),
    (r"\b(partnership|partnering|collaboration|agreement|deal with|teams up)\b", "Alianza Estratégica", "tier_2", 15),
    (r"\b(invests|stake|berkshire|buffett|institutional investment)\b", "Inversión Estratégica", "tier_2", 15),
]

TIER_3_PATTERNS = [
    (r"\b(upgrade|upgraded|target raised|buy rating|outperform|analyst)\b", "Upgrade Analista", "tier_3", 10),
    (r"\b(launch|launches|product release|expansion|expands|new market)\b", "Lanzamiento / Expansión", "tier_3", 10),
    (r"\b(conference|presentation|showcase|summit)\b", "Evento Corporativo", "tier_3", 10),
]


def classify_headline(title: str) -> Dict[str, Any]:
    """Clasifica un titular en su Tier correspondiente y retorna los puntos de bonificación."""
    lower = title.lower()

    for pattern, label, tier_code, bonus in TIER_1_PATTERNS:
        if re.search(pattern, lower):
            return {"tier": tier_code, "tier_num": 1, "label": label, "bonus": bonus, "color": "#10B981"}

    for pattern, label, tier_code, bonus in TIER_2_PATTERNS:
        if re.search(pattern, lower):
            return {"tier": tier_code, "tier_num": 2, "label": label, "bonus": bonus, "color": "#38BDF8"}

    for pattern, label, tier_code, bonus in TIER_3_PATTERNS:
        if re.search(pattern, lower):
            return {"tier": tier_code, "tier_num": 3, "label": label, "bonus": bonus, "color": "#F59E0B"}

    return {"tier": "general", "tier_num": 3, "label": "Noticia Corporativa", "bonus": 5, "color": "#94A3B8"}


def fetch_stock_news(ticker: str, max_items: int = 5) -> Dict[str, Any]:
    """
    Obtiene noticias recientes para un ticker, filtra por fecha (hoy o ayer)
    y clasifica el catalizador más relevante.
    """
    clean_ticker = ticker.replace("/", "").replace(".", "").upper().strip()
    now_ts = time.time()

    # 1. Comprobación de Cache
    cached = _NEWS_CACHE.get(clean_ticker)
    if cached and (now_ts - cached["timestamp"] < CACHE_TTL_SECONDS):
        return cached["data"]

    empty_result = {
        "ticker": clean_ticker,
        "has_news": False,
        "catalyst_badge": None,
        "catalyst_tier": 0,
        "bonus_points": 0,
        "top_headline": "",
        "top_url": "",
        "articles": [],
    }

    try:
        search_res = yf.Search(clean_ticker, news_count=max_items)
        raw_news = getattr(search_res, "news", []) or []

        if not raw_news:
            _NEWS_CACHE[clean_ticker] = {"timestamp": now_ts, "data": empty_result}
            return empty_result

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=2) # Hoy y ayer (48 horas)
        valid_articles = []
        best_catalyst = None
        highest_bonus = 0

        for item in raw_news:
            title = item.get("title", "")
            if not title:
                # Soporte para estructura nueva de yfinance
                content = item.get("content", {})
                if isinstance(content, dict):
                    title = content.get("title", "")

            if not title:
                continue

            link = item.get("link", "")
            if not link and isinstance(item.get("content"), dict):
                link = item.get("content", {}).get("canonicalUrl", {}).get("url", "")

            pub_time = item.get("providerPublishTime")
            dt_pub = None
            if pub_time:
                try:
                    dt_pub = datetime.fromtimestamp(pub_time, tz=timezone.utc)
                except Exception:
                    pass

            # Si la noticia es de más de 48 horas atrás, la descartamos
            if dt_pub and dt_pub < cutoff_date:
                continue

            pub_str = dt_pub.strftime("%d/%m %H:%M") if dt_pub else "Reciente"
            publisher = item.get("publisher") or item.get("source", "Yahoo Finance")

            cat_info = classify_headline(title)

            article_obj = {
                "title": title,
                "url": link,
                "publisher": publisher,
                "published_at": pub_str,
                "tier": cat_info["tier"],
                "label": cat_info["label"],
                "color": cat_info["color"],
                "bonus": cat_info["bonus"],
            }
            valid_articles.append(article_obj)

            if cat_info["bonus"] > highest_bonus:
                highest_bonus = cat_info["bonus"]
                best_catalyst = cat_info
                best_catalyst["headline"] = title
                best_catalyst["url"] = link

        if not valid_articles or not best_catalyst:
            _NEWS_CACHE[clean_ticker] = {"timestamp": now_ts, "data": empty_result}
            return empty_result

        result = {
            "ticker": clean_ticker,
            "has_news": True,
            "catalyst_badge": best_catalyst["label"],
            "catalyst_tier": best_catalyst["tier_num"],
            "badge_color": best_catalyst["color"],
            "bonus_points": best_catalyst["bonus"],
            "top_headline": best_catalyst["headline"],
            "top_url": best_catalyst["url"],
            "articles": valid_articles,
        }

        _NEWS_CACHE[clean_ticker] = {"timestamp": now_ts, "data": result}
        return result

    except Exception as e:
        log_warning(MODULE, f"Error obteniendo noticias para {clean_ticker}: {e}")
        return empty_result
