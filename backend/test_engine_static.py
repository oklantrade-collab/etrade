
import asyncio
import pandas as pd
from app.strategy.strategy_engine import StrategyEngine

async def test():
    # Simular contexto de ETH/SOL actuales
    contexts = {
        'ETH_actual': {
            'adx': 17.1, 'adx_velocity': 'debil',
            'plus_di': 30.0, 'minus_di': 20.0,
            'mtf_score': 0.70,
            'sar_trend_4h': 1, 'sar_trend_15m': 1,
            'sar_ini_high_15m': False,
            'fibonacci_zone': 2,
            'ema20_phase': 'nivel_2_long',
            'ema20_angle': 0.5, 'ema9_angle': 0.3,
            'pinescript_signal': 'Buy',
            'allow_long_4h': True,
            'spike_bullish': False,
            'dist_basis_pct': 2.55,
            'price': 2161.0,
            'lower_5': 2050.0, 'lower_6': 2000.0,
            'upper_5': 2250.0, 'upper_6': 2300.0,
        },
        'SOL_actual': {
            'adx': 20.9, 'adx_velocity': 'moderado',
            'plus_di': 32.0, 'minus_di': 18.0,
            'mtf_score': 0.85,
            'sar_trend_4h': 1, 'sar_trend_15m': 1,
            'sar_ini_high_15m': True,  # acaba de cambiar
            'fibonacci_zone': 1,
            'ema20_phase': 'nivel_1_long',
            'ema20_angle': 0.3, 'ema9_angle': 0.2,
            'pinescript_signal': 'Buy',
            'allow_long_4h': True,
            'spike_bullish': True,
            'dist_basis_pct': 2.85,
            'price': 91.54,
            'lower_5': 86.0, 'lower_6': 84.0,
            'upper_5': 96.0, 'upper_6': 98.0,
        }
    }

    # Crear engine sin Supabase para test
    engine = StrategyEngine(None)

    print("=== TEST STRATEGY ENGINE (STATIC) ===\n")
    for name, ctx in contexts.items():
        print(f"--- {name} ---")
        print(f"MTF: {ctx['mtf_score']} | "
              f"ADX: {ctx['adx']} ({ctx['adx_velocity']}) | "
              f"SAR4h: {ctx['sar_trend_4h']} | "
              f"Pine: {ctx['pinescript_signal']}")
        print(f"EMA20_phase: {ctx['ema20_phase']}")
        # Simular evaluación manual si tuviera reglas (pero no he cargado ninguna)
        print("Engine initialized correctly.\n")

asyncio.run(test())
