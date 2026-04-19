import json
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from app.core.logger import log_info, log_error
from app.core.config import settings
from app.core.memory_store import MEMORY_STORE
from app.candle_signals.candle_patterns import CandlePatternDetector, CandleOHLC

MODULE = "ai_candles"


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
    timeframe: str = '4h'
) -> dict:
    """
    SIPV REPLACEMENT: Analyzes candles using the local CandlePatternDetector.
    Maintains the same JSON structure as the original AI version to ensure compatibility.
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

        # 2. Build OHLCV Context
        # We prefer regular 4h data for the major interpretation
        df_4h = MEMORY_STORE.get(symbol, {}).get('4h', {}).get('df')
        target_df = df_4h if df_4h is not None and not df_4h.empty else df
        
        if target_df.empty:
            return _default_error_result()

        # Last candle and history
        last_row = target_df.iloc[-1]
        history_rows = target_df.tail(4).iloc[:-1] # at least 3 previous
        
        current_ohlc = CandleOHLC(
            open=float(last_row['open']),
            high=float(last_row['high']),
            low=float(last_row['low']),
            close=float(last_row['close']),
            volume=float(last_row.get('volume', 0))
        )
        
        history_ohlc = [
            CandleOHLC(
                open=float(r['open']),
                high=float(r['high']),
                low=float(r['low']),
                close=float(r['close']),
                volume=float(r.get('volume', 0))
            )
            for _, r in history_rows.iterrows()
        ]

        # 3. Detect Pattern using SIPV
        detector = CandlePatternDetector(market="crypto" if "USD" in symbol else "stocks")
        vol_sma = target_df['volume'].tail(20).mean() if 'volume' in target_df else None
        
        result = detector.evaluate(current_ohlc, history=history_ohlc, volume_sma20=vol_sma)

        # 4. Map SIPV Result to AI Response Schema
        sentiment = "indecision"
        if result.action == "BUY": sentiment = "bullish"
        elif result.action == "SELL": sentiment = "bearish"
        elif result.signal in ("Alcista", "Reversión Alcista"): sentiment = "bullish"
        elif result.signal in ("Bajista", "Reversión Bajista"): sentiment = "bearish"

        color = "neutral"
        if current_ohlc.is_bullish: color = "green"
        elif current_ohlc.is_bearish: color = "red"

        interpretation = f"SIPV detectó {result.pattern_name} con {result.confidence:.0f}% de confianza."
        if result.pattern_id == 0:
            interpretation = "No se detectaron patrones significativos en esta vela."

        final_res = {
            "current_candle_color": color,
            "pattern_detected": result.pattern_name,
            "pattern_confidence": round(result.confidence / 100.0, 2),
            "market_sentiment": sentiment,
            "opportune_buy": result.action == "BUY",
            "opportune_sell": result.action == "SELL",
            "candle_interpretation": interpretation,
            "recommendation": "enter" if result.action in ("BUY", "SELL") else "wait",
            "key_observation": f"Señal SIPV: {result.signal}",
            "agrees_with_signal": True, # SIPV is consistent by definition
            "from_cache": False
        }

        # 5. Save to Cache
        MEMORY_STORE[symbol]['ai_cache_15m'] = final_res
        MEMORY_STORE[symbol]['ai_cache_15m_bar'] = current_15m
        MEMORY_STORE[symbol]['ai_cache_4h'] = final_res
        
        return final_res

    except Exception as e:
        log_error(MODULE, f"SIPV interpretation error: {e}")
        return _default_error_result()

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
