"""
eTrader v2 — Gemini Sentiment Analysis
Uses CryptoPanic for news and Google Gemini API to analyse sentiment.
Never raises exceptions that block the main pipeline.
"""
import json
import os
import httpx
import google.generativeai as genai

from app.core.config import settings
from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_warning, log_error

MODULE = "sentiment"

# Configure Gemini
if settings.gemini_api_key:
    genai.configure(api_key=settings.gemini_api_key)

CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY", "")

PROMPT_TEMPLATE = """Analyze the market sentiment of these recent news headlines for {symbol} cryptocurrency.

Headlines:
{headlines}

Respond ONLY with a valid JSON object, no markdown, no explanation:
{{
  "sentiment_score": <float between -1.0 and 1.0>,
  "confidence": <float between 0.0 and 1.0>,
  "key_factors": [<list of 2-3 short strings explaining main factors>]
}}

Where sentiment_score:
-1.0 = extremely bearish
-0.5 = moderately bearish
 0.0 = neutral
+0.5 = moderately bullish
+1.0 = extremely bullish"""


def _fetch_headlines(symbol: str) -> list[str]:
    """
    Fetch recent hot headlines from CryptoPanic API.
    Returns empty list if API key not configured or call fails.
    """
    if not CRYPTOPANIC_API_KEY:
        return []

    # Extract base currency: "BTC/USDT" → "BTC", "BTCUSDT" → "BTC"
    base = symbol.split("/")[0] if "/" in symbol else symbol.replace("USDT", "")

    try:
        resp = httpx.get(
            "https://cryptopanic.com/api/v1/posts/",
            params={
                "auth_token": CRYPTOPANIC_API_KEY,
                "currencies": base,
                "filter": "hot",
                "limit": 5,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return [post["title"] for post in results[:5]]
    except Exception as e:
        log_warning(MODULE, f"CryptoPanic fetch failed for {symbol}: {e}")
        return []


def get_sentiment(
    symbol: str,
    cycle_id: str | None = None,
) -> dict:
    """
    Full sentiment analysis pipeline:
    1. Fetch headlines from CryptoPanic
    2. Analyse with Gemini
    3. Calculate adjustment for MTF score
    4. Save to Supabase

    NEVER raises exceptions. Returns neutral on any failure.
    """
    default_result = {
        "sentiment_score": 0.0,
        "confidence": 0.0,
        "key_factors": [],
        "adjustment": 0.0,
        "headlines_count": 0,
    }

    try:
        # ── STEP 1: Fetch headlines ──
        headlines = _fetch_headlines(symbol)

        # ── STEP 2: If no headlines, return neutral ──
        if not headlines:
            result = {
                "sentiment_score": 0.0,
                "confidence": 0.0,
                "key_factors": ["no_news_available"],
                "adjustment": 0.0,
                "headlines_count": 0,
            }
            # Save to DB even with no news
            _save_sentiment(symbol, [], None, result, cycle_id)
            return result

        # ── STEP 3: Call Gemini ──
        if not settings.gemini_api_key:
            log_warning(MODULE, "Gemini API key not configured — returning neutral sentiment", cycle_id=cycle_id)
            result = {
                "sentiment_score": 0.0,
                "confidence": 0.0,
                "key_factors": ["gemini_api_key_not_configured"],
                "adjustment": 0.0,
                "headlines_count": len(headlines),
            }
            _save_sentiment(symbol, headlines, None, result, cycle_id)
            return result

        # Extract base currency for prompt
        base_currency = symbol.split("/")[0] if "/" in symbol else symbol.replace("USDT", "")
        headlines_text = "\n".join([f"- {h}" for h in headlines])

        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = PROMPT_TEMPLATE.format(
            symbol=base_currency,
            headlines=headlines_text,
        )

        response = model.generate_content(prompt)
        raw_text = response.text.strip()

        # ── STEP 4: Parse Gemini response ──
        text = raw_text.replace("```json", "").replace("```", "").strip()

        try:
            parsed = json.loads(text)
            sentiment_score = float(parsed.get("sentiment_score", 0.0))
            confidence = float(parsed.get("confidence", 0.0))
            key_factors = parsed.get("key_factors", [])

            # Clamp to valid ranges
            sentiment_score = max(-1.0, min(1.0, sentiment_score))
            confidence = max(0.0, min(1.0, confidence))
        except Exception as e:
            log_warning(MODULE, f"Failed to parse Gemini response: {e}", cycle_id=cycle_id)
            sentiment_score = 0.0
            confidence = 0.0
            key_factors = [f"gemini_parse_error: {str(e)}"]

        # ── STEP 5: Calculate adjustment ──
        # Max influence of ±0.05 on MTF score
        adjustment = sentiment_score * 0.05
        adjustment = round(adjustment, 4)

        result = {
            "sentiment_score": sentiment_score,
            "confidence": confidence,
            "key_factors": key_factors,
            "adjustment": adjustment,
            "headlines_count": len(headlines),
        }

        # ── STEP 6: Save to Supabase ──
        _save_sentiment(symbol, headlines, raw_text, result, cycle_id)

        log_info(
            MODULE,
            f"Sentiment for {symbol}: score={sentiment_score:+.2f} "
            f"confidence={confidence:.2f} adj={adjustment:+.4f} "
            f"factors={key_factors}",
            result,
            cycle_id,
        )

        return result

    except Exception as e:
        # NEVER block the pipeline
        log_error(MODULE, f"Sentiment analysis failed for {symbol}: {e}", cycle_id=cycle_id)
        return default_result


def _save_sentiment(
    symbol: str,
    headlines: list[str],
    raw_response: str | None,
    result: dict,
    cycle_id: str | None,
):
    """Persist sentiment analysis to news_sentiment table."""
    try:
        from app.analysis.data_fetcher import to_internal_symbol

        internal_sym = to_internal_symbol(symbol) if "/" not in symbol else symbol

        sb = get_supabase()
        row = {
            "symbol": internal_sym,
            "cycle_id": cycle_id or "00000000-0000-0000-0000-000000000000",
            "news_headlines": headlines,
            "gemini_response": raw_response,
            "sentiment_score": result.get("sentiment_score", 0.0),
            "confidence": result.get("confidence", 0.0),
            "key_factors": result.get("key_factors", []),
        }
        sb.table("news_sentiment").insert(row).execute()
    except Exception as e:
        log_warning(MODULE, f"Failed to save sentiment to DB: {e}", cycle_id=cycle_id)
