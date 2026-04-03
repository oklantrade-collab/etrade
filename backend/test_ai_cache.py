import asyncio
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
import sys
import os

# Ensure backend root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analysis.ai_candles import (
    interpret_candles_with_ai,
    get_current_4h_bar
)
from app.core.memory_store import MEMORY_STORE

async def run_test():
    # Simular que ya hay un resultado cacheado para la vela actual
    symbol = 'BTCUSDT'
    if symbol not in MEMORY_STORE:
        MEMORY_STORE[symbol] = {}
        
    current_4h = get_current_4h_bar()
    MEMORY_STORE[symbol]['ai_cache_4h_bar'] = current_4h
    MEMORY_STORE[symbol]['ai_cache_4h'] = {
        'recommendation':      'enter',
        'market_sentiment':    'bullish',
        'pattern_confidence':  0.75,
        'candle_interpretation': 'Tendencia alcista confirmada.',
        'agrees_with_signal':  True,
        'key_observation':     'Velas con cuerpo sólido alcista.',
    }

    # Llamar 3 veces en la misma vela de 4h
    # Mock parameters that are not needed when using cache
    df = MagicMock()
    levels = {}
    regime = {}
    
    for i in range(3):
        result = interpret_candles_with_ai(
            symbol, df, levels, regime, 
            ema20_phase='bullish', adx_value=25.0, 
            signal_direction='long'
        )
        assert result.get('from_cache') == True, \
            f"Llamada {i+1}: debería usar caché pero llamó a la API"
        print(f"Llamada {i+1}: from_cache=True OK")

    print("\nRESULTADO: Claude no fue llamado en las 3 invocaciones")
    print("Cache de 4h funcionando correctamente")

if __name__ == "__main__":
    asyncio.run(run_test())
