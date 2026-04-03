import json
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from app.core.logger import log_info, log_error
from app.core.config import settings
from app.core.memory_store import MEMORY_STORE

MODULE = "ai_candles"

def get_current_4h_bar(ts: datetime = None) -> datetime:
    """Retorna el inicio de la vela de 4h actual."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    hour_4h = (ts.hour // 4) * 4
    return ts.replace(hour=hour_4h, minute=0, second=0, microsecond=0)

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
    Contextual second opinion on market behavior using Claude cached for 4 hours.
    MEJORA 1: Cache de 4h para reducir costos.
    """
    try:
        current_4h = get_current_4h_bar()
        
        # 1. Check Cache
        if symbol not in MEMORY_STORE:
            MEMORY_STORE[symbol] = {}
            
        cached_bar = MEMORY_STORE[symbol].get('ai_cache_4h_bar')
        if cached_bar == current_4h:
            cached = MEMORY_STORE[symbol].get('ai_cache_4h')
            if cached:
                cached['from_cache'] = True
                return cached

        # 2. Build Context using 4h candles
        # DESPUÉS: Usar velas de 4h como contexto para Claude
        df_4h = MEMORY_STORE.get(symbol, {}).get('4h', {}).get('df')
        if df_4h is not None and not df_4h.empty:
            last_5 = df_4h.tail(5)[['open', 'high', 'low', 'close', 'volume']].copy()
        else:
            # Fallback if 4h data is not available yet
            last_5 = df.tail(5)[["open", "high", "low", "close", "volume"]].copy()
            
        candles_table = last_5.to_string()

        prompt = f"""Eres un analista técnico experto en criptomonedas.
Analiza las últimas 5 velas de 4h y el contexto de mercado proporcionado.
Responde ÚNICAMENTE en JSON válido sin markdown ni texto explicativo.

CONTEXTO DE MERCADO:
- Símbolo: {symbol}
- Régimen: {regime.get('category', 'desconocido')} (Score: {regime.get('risk_score', 0)})
- Fase EMA20: {ema20_phase}
- ADX: {adx_value:.2f}
- Zona Fibonacci: {levels.get('zone', 0)} (Basis: {levels.get('basis', 0):.2f})
- Niveles Fibonacci: Upper_5: {levels.get('upper_5', 0):.2f}, Upper_6: {levels.get('upper_6', 0):.2f}, Lower_5: {levels.get('lower_5', 0):.2f}, Lower_6: {levels.get('lower_6', 0):.2f}
- Señal Pinescript del Sistema: {signal_direction or "None"}

ÚLTIMAS 5 VELAS (4h):
{candles_table}

ESTRUCTURA DE RESPUESTA REQUERIDA (JSON):
{{
  "pattern_detected": "nombre del patrón en español",
  "pattern_confidence": 0.0 a 1.0,
  "market_sentiment": "bullish|bearish|indecision|reversal",
  "candle_interpretation": "descripción en español, máx 2 oraciones",
  "agrees_with_signal": true|false|null,
  "recommendation": "enter|wait|caution",
  "key_observation": "observación principal, 1 oración"
}}

Si no hay señal (pinescript_signal=None), agrees_with_signal debe ser null y recommendation "wait".
"""
        # 3. Call Anthropic API
        try:
            import anthropic
        except ImportError:
            log_error(MODULE, "Anthropic module not installed. AI interpretation disabled.")
            return _default_error_result()
            
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        
        response = await client.messages.create(
            model="claude-sonnet-4-20250514", 
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
            timeout=15.0
        )

        try:
            content = response.content[0].text
            # Clean possible markdown wrap
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            result = json.loads(content)
        except Exception as parse_err:
            log_error(MODULE, f"JSON Parse Error: {parse_err} | Raw: {response.content[0].text}")
            result = _default_error_result()

        # 4. Save to Cache
        result['from_cache'] = False
        MEMORY_STORE[symbol]['ai_cache_4h'] = result
        MEMORY_STORE[symbol]['ai_cache_4h_bar'] = current_4h
        
        return result

    except Exception as e:
        log_error(MODULE, f"AI Error: {e}")
        return _default_error_result()

def _default_error_result() -> dict:
    return {
        "pattern_detected": "error",
        "pattern_confidence": 0.0,
        "market_sentiment": "indecision",
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
