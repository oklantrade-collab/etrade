"""
eTrade v6.0 — CATALYST & NEWS CLASSIFIER (APIs + IBKR)
======================================================
Clasificador de noticias y eventos corporativos para acciones.
Distingue el combustible real de un movimiento y detecta el peligro de dilución inmediata.

Niveles de Catalizador:
- Tier 0: PELIGRO TÓXICO DE DILUCIÓN (Public Offering, Warrants, ATM, S-3, Delisting).
          -> Veto incondicional en Trap Shield.
- Tier 1: MÁXIMO IMPACTO (+80% a +200%+): Aprobación FDA, Fase 3 clínica exitosa, M&A/Adquisición, Contratos de Defensa.
- Tier 2: MEDIO IMPACTO (+30% a +80%): Resultados de utilidades récord, Guía alcista (Earnings Beat), Alianza estratégica/AI.
- Tier 3: GENERAL / PR COMÚN: Notas de prensa rutinarias, conferencias de inversores.
"""

from typing import Dict, Any, List, Optional
import re
from app.core.logger import log_info, log_warning, log_error

MODULE = "CATALYST_CLASSIFIER"

# Patrones regex para detección
TIER_0_TOXIC = [
    r'public offering', r'direct offering', r'registered direct',
    r'pricing of offering', r'warrants?\b', r'atm offering', r'at-the-market',
    r'equity distribution agreement', r'dilution', r'reverse (stock )?split',
    r'delisting notice', r'nasdaq non-compliance', r'subpoena',
    r'sec investigation', r'chapter 11', r'bankruptcy', r'\bs-3\b'
]

TIER_1_SUPER = [
    r'fda approv\w*', r'fda clears?', r'breakthrough therapy',
    r'phase 3 (trial|study)?', r'primary endpoint met', r'pivotal trial',
    r'acquisition of', r'merger with', r'merger agreement', r'buyout',
    r'takeover offer', r'defense contract', r'department of defense',
    r'patent granted', r'breakthrough designation', r'new drug application'
]

TIER_2_GROWTH = [
    r'earnings beat', r'reports q[1-4] results', r'record revenue',
    r'beats estimates', r'raises guidance', r'strategic partnership',
    r'commercial deployment', r'ai powered', r'joint venture',
    r'debt elimination', r'litigation settled', r'corexa'
]


def classify_catalyst_text(headline: str, summary: str = "") -> dict:
    """Clasifica el texto de un titular o nota de prensa en su respectivo Tier."""
    combined = f"{headline} {summary}".lower()

    # 1. Verificar Peligro Tóxico (Tier 0)
    for pattern in TIER_0_TOXIC:
        if re.search(pattern, combined):
            return {
                'tier': 0,
                'is_toxic': True,
                'catalyst_name': 'TOXIC_DILUTION_RISK',
                'matched_pattern': pattern,
                'headline': headline,
                'impact_score': -50,
                'reason': f"Alerta de Dilución / Emisión de Acciones detectada ({pattern})."
            }

    # 2. Verificar Máximo Impacto (Tier 1)
    for pattern in TIER_1_SUPER:
        if re.search(pattern, combined):
            return {
                'tier': 1,
                'is_toxic': False,
                'catalyst_name': 'TIER_1_TRANSFORMATIVE',
                'matched_pattern': pattern,
                'headline': headline,
                'impact_score': 95,
                'reason': f"Catalizador transformador de alto impacto confirmado ({pattern})."
            }

    # 3. Verificar Alto Crecimiento (Tier 2)
    for pattern in TIER_2_GROWTH:
        if re.search(pattern, combined):
            return {
                'tier': 2,
                'is_toxic': False,
                'catalyst_name': 'TIER_2_EXPANSION',
                'matched_pattern': pattern,
                'headline': headline,
                'impact_score': 75,
                'reason': f"Noticia comercial / resultados de expansión positiva ({pattern})."
            }

    return {
        'tier': 3,
        'is_toxic': False,
        'catalyst_name': 'TIER_3_GENERAL',
        'matched_pattern': None,
        'headline': headline,
        'impact_score': 50,
        'reason': "Nota de prensa general sin catalizador de alta volatilidad."
    }


def analyze_news_items(news_list: Optional[List[dict]]) -> dict:
    """Evalúa una lista de noticias para un ticker y retorna el catalizador dominante."""
    import time
    now_ts = time.time()

    if not news_list:
        return {
            'tier': 2,
            'is_toxic': False,
            'catalyst_name': 'NO_RECENT_NEWS',
            'headline': 'Sin noticias recientes',
            'impact_score': 50,
            'reason': 'Sin feed de noticias en las últimas 24h.'
        }

    dominant = None
    for item in news_list[:6]:
        title = item.get('title') or item.get('headline') or ''
        summary = item.get('summary') or ''
        pub_time = float(item.get('publish_time') or 0.0)
        age_hours = ((now_ts - pub_time) / 3600.0) if pub_time > 0 else 0.0

        res = classify_catalyst_text(title, summary)
        
        # Filtro de Antigüedad para Veto Tóxico (Tier 0):
        # Solo vetar si la noticia de dilución ocurrió en las últimas 48 horas.
        # Noticias antiguas (ej. un reverse split de hace semanas/meses) son irrelevantes para el momentum de hoy.
        if res['tier'] == 0:
            if pub_time > 0 and age_hours > 48.0:
                log_info(MODULE, f"Ignorando veto tóxico histórico ({age_hours:.1f}h > 48h): '{title[:70]}'")
                continue
            return res  # Veto legítimo de dilución reciente (<48h)
            
        if dominant is None or res['tier'] < dominant['tier']:
            dominant = res

    return dominant or {
        'tier': 3,
        'is_toxic': False,
        'catalyst_name': 'GENERAL_NEWS',
        'headline': 'Noticias generales',
        'impact_score': 50,
        'reason': 'Noticias estándar de mercado.'
    }


def fetch_ticker_news(ticker: str, max_items: int = 5) -> List[dict]:
    """
    Descarga los titulares de noticias más recientes para un ticker.
    Utiliza yfinance Search (con fallback) para alimentar el clasificador de catalizadores.
    """
    if not ticker:
        return []
    try:
        import yfinance as yf
        s = yf.Search(ticker, news_count=max_items)
        raw_news = getattr(s, 'news', []) or []
        items = []
        for n in raw_news[:max_items]:
            title = n.get('title') or ''
            publisher = n.get('publisher') or ''
            link = n.get('link') or ''
            summary = n.get('summary') or publisher
            pub_time = int(n.get('providerPublishTime') or 0)
            if title:
                items.append({
                    'title': title,
                    'summary': summary,
                    'publisher': publisher,
                    'link': link,
                    'publish_time': pub_time
                })
        return items
    except Exception as e:
        log_warning(MODULE, f"Error descargando noticias para {ticker}: {e}")
        return []


def analyze_ticker_live_catalyst(ticker: str, news_list: Optional[List[dict]] = None) -> dict:
    """Obtiene noticias en vivo (si no se pasan) y clasifica el catalizador del ticker."""
    items = news_list if news_list else fetch_ticker_news(ticker, max_items=5)
    return analyze_news_items(items)

