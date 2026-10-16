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


# Diccionario y reglas de traducción financiera de inglés a español
TRANSLATION_RULES = [
    (r"\bEarnings Call Highlights\b", "Lo más destacado de la llamada de resultados"),
    (r"\bEarnings Call Transcript\b", "Transcripción de la llamada de resultados"),
    (r"\bEarnings Call\b", "Llamada de resultados"),
    (r"\bStocks to Watch\b", "Acciones a seguir"),
    (r"\bStock Rises Overnight\b", "La acción sube durante la noche"),
    (r"\bStock Rises\b", "La acción sube"),
    (r"\bStock Jumps\b", "La acción salta al alza"),
    (r"\bStock Surges\b", "La acción se dispara"),
    (r"\bStock Soars\b", "La acción se eleva con fuerza"),
    (r"\bStock Tumbles\b", "La acción cae con fuerza"),
    (r"\bStock Falls\b", "La acción retrocede"),
    (r"\bCost Pressures\b", "presiones de costos"),
    (r"\bStrong Cash Flow\b", "fuerte flujo de caja"),
    (r"\bStrategic Growth\b", "crecimiento estratégico"),
    (r"\bAmid\b", "en medio de"),
    (r"\bTarget Raised\b", "precio objetivo elevado"),
    (r"\bUpgraded to Buy\b", "mejorada a recomendación de compra"),
    (r"\bWins Contract\b", "gana contrato multimillonario"),
    (r"\bSecures Agreement\b", "asegura acuerdo estratégico"),
    (r"\bFDA Approval\b", "aprobación de la FDA"),
    (r"\bFDA Clearance\b", "autorización médica de la FDA"),
    (r"\bClinical Trial\b", "ensayo clínico"),
    (r"\bQ([1-4])\b", r"Trimestre \1 (Q\1)"),
    (r"\bRevenue Beat\b", "supera expectativas de ingresos"),
    (r"\bEPS Beat\b", "supera estimaciones de beneficio por acción"),
    (r"\bPartnership\b", "alianza estratégica"),
    (r"\bAcquisition\b", "adquisición corporativa"),
    (r"\bMerger\b", "fusión empresarial"),
]

def translate_headline_es(title: str) -> str:
    """Traduce un titular financiero del inglés al español de forma natural."""
    if not title:
        return ""
    res = title
    for pat, rep in TRANSLATION_RULES:
        res = re.sub(pat, rep, res, flags=re.IGNORECASE)
    # Reemplazos de palabras sueltas comunes
    word_replacements = {
        "Highlights": "Destaca",
        "Highlights:": "Destaca:",
        "Deal": "Acuerdo",
        "Deals": "Acuerdos",
        "Agreement": "Acuerdo",
        "Results": "Resultados",
        "Reported": "Reportó",
        "Reports": "Reporta",
        "Announces": "Anuncia",
        "Announced": "Anunció",
        "Quarterly": "Trimestral",
        "Full Year": "Año Completo",
        "Guidance": "Proyección Anual",
        "Profit": "Beneficio",
        "Revenue": "Ingresos",
        "Contract": "Contrato",
        "Awarded": "Adjudicado",
        "Defense": "Defensa",
        "Shares": "Acciones",
        "Market": "Mercado",
        "Growth": "Crecimiento",
        "Outlook": "Perspectiva",
        "Investor": "Inversionista",
        "Investors": "Inversionistas",
    }
    for eng, esp in word_replacements.items():
        res = re.sub(rf"\b{eng}\b", esp, res)
    return res.strip()


_AI_API_DISABLED_UNTIL = 0.0

def evaluate_catalyst_with_ai(ticker: str, company_name: str, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evalúa semánticamente el catalizador con IA (OpenAI / Gemini) o heurística avanzada.
    Genera una síntesis ejecutiva en español y un puntaje cuantitativo (0 a 30).
    """
    global _AI_API_DISABLED_UNTIL
    from app.core.config import settings

    # Heurística inicial por defecto
    best_bonus = max([a.get("bonus", 5) for a in articles], default=5)
    best_label = articles[0].get("label", "Noticia Corporativa") if articles else "Sin Catalizador"
    default_summary = f"{ticker}: Impulso respaldado por {best_label}. Actividad de noticias en las últimas 48 horas con interés comprador."

    # Intentar análisis con LLM si API key de OpenAI está configurada y no está en cooldown
    now_ts = time.time()
    if settings.openai_api_key and articles and (now_ts > _AI_API_DISABLED_UNTIL):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
            titles_text = "\n".join([f"- {a.get('title')}" for a in articles[:4]])

            prompt = (
                f"Analiza estas noticias recientes para la acción {ticker} ({company_name}):\n"
                f"{titles_text}\n\n"
                f"Responde estrictamente en formato JSON sin formato adicional ni markdown:\n"
                f'{{"summary_es": "<explicación en 1-2 líneas en español de por qué sube la acción y cuál es el catalizador real>", '
                f'"score": <entero entre 10 y 30 según la magnitud económica del catalizador>, '
                f'"catalyst_type": "<Contrato / IA / FDA / Earnings / M&A / etc.>"}}'
            )

            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                timeout=3.0,
                temperature=0.2,
                max_tokens=150
            )
            raw_content = resp.choices[0].message.content.strip()
            # Limpiar posible bloque de markdown
            if "```" in raw_content:
                raw_content = raw_content.split("```")[1].replace("json", "").strip()

            import json
            data = json.loads(raw_content)
            return {
                "summary_es": data.get("summary_es") or default_summary,
                "score": int(data.get("score") or best_bonus),
                "type": data.get("catalyst_type") or best_label,
            }
        except Exception as ai_e:
            err_str = str(ai_e).lower()
            if "429" in err_str or "quota" in err_str or "billing" in err_str:
                _AI_API_DISABLED_UNTIL = now_ts + 3600.0  # 1 hora de cooldown para evitar lentitud
                log_warning(MODULE, f"OpenAI quota agotada. Activando motor heurístico por 1h: {ai_e}")
            else:
                log_warning(MODULE, f"Fallback de IA para {ticker}: {ai_e}")

    # Fallback heurístico inteligente
    first_title = articles[0].get("title", "") if articles else ""
    first_title_es = translate_headline_es(first_title)
    if "Earnings" in first_title or "Resultados" in best_label:
        default_summary = f"{company_name} ({ticker}) reportó resultados trimestrales con catalizadores positivos destacados en su informe corporativo."
    elif "FDA" in best_label or "Aprobación" in best_label:
        default_summary = f"{company_name} ({ticker}) cuenta con avance regulatorio y catalizador de aprobación médica ante la FDA."
    elif "Contrato" in best_label or "M&A" in best_label:
        default_summary = f"{company_name} ({ticker}) cerró un acuerdo contractual o adquisición relevante que expande sus ingresos previstos."
    elif first_title_es:
        default_summary = f"{ticker}: {first_title_es}"

    return {
        "summary_es": default_summary,
        "score": best_bonus,
        "type": best_label,
    }


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

        # Traducir los titulares al español para cada artículo
        for art in valid_articles:
            art["title_es"] = translate_headline_es(art.get("title", ""))
            art["summary_es"] = f"Noticia ({art.get('label')}) reportada por {art.get('publisher')}."

        # Evaluación semántica del catalizador con IA / Heurística
        ai_eval = evaluate_catalyst_with_ai(clean_ticker, clean_ticker, valid_articles)
        catalyst_summary_es = ai_eval.get("summary_es", "")
        final_bonus = max(highest_bonus, ai_eval.get("score", highest_bonus))

        result = {
            "ticker": clean_ticker,
            "has_news": True,
            "catalyst_badge": best_catalyst["label"],
            "catalyst_tier": best_catalyst["tier_num"],
            "badge_color": best_catalyst["color"],
            "bonus_points": final_bonus,
            "top_headline": best_catalyst["headline"],
            "top_headline_es": translate_headline_es(best_catalyst["headline"]),
            "catalyst_summary_es": catalyst_summary_es,
            "top_url": best_catalyst["url"],
            "articles": valid_articles,
        }

        _NEWS_CACHE[clean_ticker] = {"timestamp": now_ts, "data": result}
        return result

    except Exception as e:
        log_warning(MODULE, f"Error obteniendo noticias para {clean_ticker}: {e}")
        return empty_result
