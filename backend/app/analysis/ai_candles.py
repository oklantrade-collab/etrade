import json
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import google.generativeai as genai

from app.core.logger import log_info, log_error
from app.core.config import settings
from app.core.memory_store import MEMORY_STORE

MODULE = "ai_candles"

# Configure Gemini
if settings.gemini_api_key:
    genai.configure(api_key=settings.gemini_api_key)

def get_current_15m_bar(ts: datetime = None) -> datetime:
    """Retorna el inicio de la vela de 15m actual para cache."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    minute_15 = (ts.minute // 15) * 15
    return ts.replace(minute=minute_15, second=0, microsecond=0)

async def interpret_candles_with_ai(
    symbol: str,
    df: pd.DataFrame,
    levels: dict,
    regime: dict,
    ema20_phase: str,
    adx_value: float,
    signal_direction: Optional[str] = None,
    timeframe: str = '15m'
) -> dict:
    """
    Contextual second opinion on market behavior using Gemini Flash (Optimized for cost).
    Actualizado cada 15m para reflejar el estado actual de la vela de 4h.
    """
    try:
        current_15m = get_current_15m_bar()
        
        # 1. Check Cache
        if symbol not in MEMORY_STORE:
            MEMORY_STORE[symbol] = {}
            
        cached_bar = MEMORY_STORE[symbol].get('ai_cache_15m_bar')
        if cached_bar == current_15m:
            cached = MEMORY_STORE[symbol].get('ai_cache_15m')
            if cached:
                cached['from_cache'] = True
                return cached

        # 2. Build Context using 4h candles
        df_4h = MEMORY_STORE.get(symbol, {}).get('4h', {}).get('df')
        if df_4h is not None and not df_4h.empty:
            last_5 = df_4h.tail(5)[['open', 'high', 'low', 'close', 'volume']].copy()
        else:
            last_5 = df.tail(5)[["open", "high", "low", "close", "volume"]].copy()
            
        candles_table = last_5.to_string()

        prompt = f"""Eres un analista técnico experto en trading.
Analiza la vela de 4h actual y las 4 previas para {symbol}.
Responde ÚNICAMENTE en JSON válido.

CONTEXTO DE MERCADO:
- Régimen: {regime.get('category', 'desconocido')} (Score: {regime.get('risk_score', 0)})
- Fase EMA20: {ema20_phase}
- ADX: {adx_value:.2f}
- Zona Fibonacci: {levels.get('zone', 0)} (Basis: {levels.get('basis', 0):.2f})
- Señal Pinescript del Sistema: {signal_direction or "None"}

ÚLTIMAS 5 VELAS (4h):
{candles_table}

ESTRUCTURA DE RESPUESTA REQUERIDA (JSON):
{{
  "current_candle_color": "red|green|neutral",
  "pattern_detected": "nombre del patrón",
  "pattern_confidence": 0.0 a 1.0,
  "market_sentiment": "bullish|bearish|indecision|reversal",
  "opportune_buy": true|false,
  "opportune_sell": true|false,
  "candle_interpretation": "máx 2 oraciones",
  "recommendation": "enter|wait|caution",
  "key_observation": "1 oración"
}}
"""
        # 3. Call Gemini API
        if not settings.gemini_api_key:
            log_error(MODULE, "Gemini API key not configured - AI interpretation disabled.")
            return _default_error_result()

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = await model.generate_content_async(prompt)
            content = response.text.strip()
            
            # Clean JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
            # Normalize for binding compatibility
            result['agrees_with_signal'] = True # Default to true unless we add logic
            
        except Exception as api_err:
            log_error(MODULE, f"Gemini API/Parse Error: {api_err}")
            result = _default_error_result()

        # 4. Save to Cache
        result['from_cache'] = False
        MEMORY_STORE[symbol]['ai_cache_15m'] = result
        MEMORY_STORE[symbol]['ai_cache_15m_bar'] = current_15m
        
        # Compatibility with existing code expecting ai_cache_4h
        MEMORY_STORE[symbol]['ai_cache_4h'] = result
        
        return result

    except Exception as e:
        log_error(MODULE, f"AI Error: {e}")
        return _default_error_result()

def _default_error_result() -> dict:
    return {
        "current_candle_color": "neutral",
        "pattern_detected": "error",
        "pattern_confidence": 0.0,
        "market_sentiment": "indecision",
        "opportune_buy": False,
        "opportune_sell": False,
        "candle_interpretation": "Interpretación no disponible",
        "agrees_with_signal": None,
        "recommendation": "wait",
        "key_observation": "Error en API de IA",
        "from_cache": False
    }

def apply_ai_binding(
    ai_result:       dict,
    signal_direction: str,   # 'long' | 'short'
    min_confidence:  float = 0.40
) -> dict:
    """
    Modo binding — veto binario por contradicción de dirección.
    MEJORA 2: Simplificar modo binding de IA con regla de veto binario.
    """
    confidence  = ai_result.get('pattern_confidence', 0)
    sentiment   = ai_result.get('market_sentiment', 'indecision')
    agrees      = ai_result.get('agrees_with_signal', True)
    observation = ai_result.get('key_observation', '')

    # Baja confianza → ignorar recomendación, dejar pasar
    if confidence < min_confidence:
        return {
            'action':  'enter',
            'reason':  f'IA ignorada — confianza baja ({confidence:.0%})',
            'ai_used': False,
            'blocked': False
        }

    # Detectar contradicción de dirección
    contradiction = False

    if signal_direction == 'long':
        if sentiment == 'bearish':
            contradiction = True
        if sentiment == 'reversal' and not agrees:
            contradiction = True

    if signal_direction == 'short':
        if sentiment == 'bullish':
            contradiction = True
        if sentiment == 'reversal' and not agrees:
            contradiction = True

    if contradiction:
        return {
            'action':  'block',
            'reason':  (
                f'IA vetó entrada {signal_direction.upper()} — '
                f'mercado detectado como {sentiment}. '
                f'{observation}'
            ),
            'ai_used': True,
            'blocked': True
        }

    # Sin contradicción → dejar pasar
    return {
        'action':  'enter',
        'reason':  f'IA confirma o es neutral ({sentiment})',
        'ai_used': True,
        'blocked': False
    }
