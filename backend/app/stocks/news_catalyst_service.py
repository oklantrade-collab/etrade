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
    Evalúa semánticamente el catalizador con IA (Gemini / OpenAI) o heurística avanzada.
    Genera síntesis ejecutiva, puntaje cuantitativo, justificación y detección de catalizadores ocultos.
    """
    global _AI_API_DISABLED_UNTIL
    from app.core.config import settings

    best_bonus = max([a.get("bonus", 5) for a in articles], default=5)
    best_label = articles[0].get("label", "Noticia Corporativa") if articles else "Sin Catalizador"
    titles_text = "\n".join([f"- {a.get('title')}" for a in articles[:4]])

    # Heurística inicial inteligente de respaldo
    if "Earnings" in titles_text or "Resultados" in best_label:
        default_summary = f"{company_name} ({ticker}) reportó resultados trimestrales con catalizadores positivos destacados en su informe corporativo."
        default_justification = f"Puntuación de +{best_bonus} pts otorgada por superación de expectativas (Earnings Beat) o guía favorable, sustentando el crecimiento de márgenes operativos."
        default_hidden = "Posible cobertura forzada de posiciones cortas institucionales (Short Squeeze) tras invalidar tesis bajistas con cifras de facturación."
        default_impact = "MODERADO A ALTO (+10% a +25%)"
    elif "FDA" in best_label or "Aprobación" in best_label or "Clinical" in titles_text:
        default_summary = f"{company_name} ({ticker}) cuenta con avance regulatorio y catalizador de aprobación médica ante la FDA."
        default_justification = f"Puntuación de +{best_bonus} pts otorgada por tratarse de un catalizador regulatorio de primer orden (FDA / Ensayo Clínico). Genera barrera de entrada comercial y flujo de ingresos recurrente."
        default_hidden = "Estructura de bajo float típica en biotecnológicas: la noticia médica atrae volumen institucional que agota la oferta flotante, proyectando continuidad del rally intradía."
        default_impact = "ALTO / EXPLOSIVO (+20% a +75%)"
    elif "Contrato" in best_label or "M&A" in best_label or "Acuerdo" in best_label:
        default_summary = f"{company_name} ({ticker}) cerró un acuerdo contractual o adquisición relevante que expande sus ingresos previstos."
        default_justification = f"Puntuación de +{best_bonus} pts asignada por acuerdo contractual vinculante o alianza estratégica que impacta de inmediato en la facturación y backlog."
        default_hidden = "Posible revisión al alza de precio objetivo y recomendaciones por analistas de Wall Street en las próximas 24 a 48 horas."
        default_impact = "ALTO (+15% a +35%)"
    else:
        first_title = articles[0].get("title", "") if articles else ""
        first_title_es = translate_headline_es(first_title)
        default_summary = f"{ticker}: {first_title_es or 'Impulso respaldado por noticias corporativas recientes.'}"
        default_justification = f"Puntuación base de +{best_bonus} pts asignada por cobertura informativa positiva en medios financieros y flujo de liquidez."
        default_hidden = "Interés especulativo y aumento sostenido de volumen relativo (RVOL) por encima de la media histórica del activo."
        default_impact = "MODERADO (+5% a +15%)"

    now_ts = time.time()

    # 1. Intentar con Google Gemini (Prioridad solicitada por el usuario)
    if settings.gemini_api_key and articles and (now_ts > _AI_API_DISABLED_UNTIL):
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")

            prompt = (
                f"Actúa como analista senior de Wall Street y momentum trader. Analiza estas noticias de hoy para {ticker} ({company_name}):\n"
                f"{titles_text}\n\n"
                f"Responde estrictamente en formato JSON válido (sin backticks ```json ni texto adicional):\n"
                f"{{\n"
                f'  "summary_es": "<resumen ejecutivo en español en 1-2 líneas de qué ocurrió y cuál es el catalizador>",\n'
                f'  "score": <entero entre 10 y 30 según el impacto del catalizador>,\n'
                f'  "catalyst_type": "<tipo: FDA / Contrato / Earnings / M&A / IA / etc>",\n'
                f'  "score_justification": "<justificación detallada y profesional de por qué se asignó esta puntuación y su impacto financiero>",\n'
                f'  "hidden_catalyst": "<identifica si hay un catalizador oculto o secundario (bajo float, short interest, contrato no descontado, sin resistencia técnica) que proyecte un incremento de precio considerable>",\n'
                f'  "projected_impact": "<ALTO (+20% a +60%) | MODERADO (+8% a +20%) | EXPLOSIVO (+60%+)>"\n'
                f"}}"
            )

            resp = model.generate_content(prompt)
            raw = (resp.text or "").strip()
            if "```" in raw:
                raw = raw.split("```")[1].replace("json", "").strip()

            import json
            data = json.loads(raw)
            return {
                "summary_es": data.get("summary_es") or default_summary,
                "score": int(data.get("score") or best_bonus),
                "type": data.get("catalyst_type") or best_label,
                "score_justification": data.get("score_justification") or default_justification,
                "hidden_catalyst": data.get("hidden_catalyst") or default_hidden,
                "projected_impact": data.get("projected_impact") or default_impact,
                "source_model": "Gemini 1.5 Flash",
            }
        except Exception as gem_e:
            err_str = str(gem_e).lower()
            if "429" in err_str or "quota" in err_str:
                _AI_API_DISABLED_UNTIL = now_ts + 1800.0
            log_warning(MODULE, f"Gemini catalyst analysis fallback for {ticker}: {gem_e}")

    # 2. Intentar con OpenAI como fallback
    if settings.openai_api_key and articles and (now_ts > _AI_API_DISABLED_UNTIL):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key, max_retries=0)

            prompt = (
                f"Analiza estas noticias recientes para la acción {ticker} ({company_name}):\n"
                f"{titles_text}\n\n"
                f"Responde estrictamente en JSON:\n"
                f'{{"summary_es": "<explicación en español>", '
                f'"score": <entero 10 a 30>, '
                f'"catalyst_type": "<tipo>", '
                f'"score_justification": "<justificación de la puntuación asignada>", '
                f'"hidden_catalyst": "<catalizador oculto que proyecte subida>", '
                f'"projected_impact": "<ALTO | MODERADO | EXPLOSIVO>"}}'
            )

            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                timeout=3.0,
                temperature=0.2,
                max_tokens=220
            )
            raw_content = resp.choices[0].message.content.strip()
            if "```" in raw_content:
                raw_content = raw_content.split("```")[1].replace("json", "").strip()

            import json
            data = json.loads(raw_content)
            return {
                "summary_es": data.get("summary_es") or default_summary,
                "score": int(data.get("score") or best_bonus),
                "type": data.get("catalyst_type") or best_label,
                "score_justification": data.get("score_justification") or default_justification,
                "hidden_catalyst": data.get("hidden_catalyst") or default_hidden,
                "projected_impact": data.get("projected_impact") or default_impact,
                "source_model": "OpenAI GPT-4o-mini",
            }
        except Exception as ai_e:
            err_str = str(ai_e).lower()
            if "429" in err_str or "quota" in err_str:
                _AI_API_DISABLED_UNTIL = now_ts + 3600.0
            log_warning(MODULE, f"OpenAI fallback for {ticker}: {ai_e}")

    return {
        "summary_es": default_summary,
        "score": best_bonus,
        "type": best_label,
        "score_justification": default_justification,
        "hidden_catalyst": default_hidden,
        "projected_impact": default_impact,
        "source_model": "Motor Cuantitativo eTrader",
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
            "score_justification": ai_eval.get("score_justification", ""),
            "hidden_catalyst": ai_eval.get("hidden_catalyst", ""),
            "projected_impact": ai_eval.get("projected_impact", "MODERADO"),
            "source_model": ai_eval.get("source_model", "Gemini AI"),
            "top_url": best_catalyst["url"],
            "articles": valid_articles,
        }

        _NEWS_CACHE[clean_ticker] = {"timestamp": now_ts, "data": result}
        return result

    except Exception as e:
        log_warning(MODULE, f"Error obteniendo noticias para {clean_ticker}: {e}")
        return empty_result
