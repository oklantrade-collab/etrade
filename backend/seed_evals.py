
import asyncio, os
from dotenv import load_dotenv
from supabase import create_client
from app.strategy.strategy_engine import StrategyEngine

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

async def main():
    engine = StrategyEngine(sb)
    await engine.load()

    # Simular contexto favorable ETH
    context = {
        'symbol': 'ETHUSDT', 'price': 2161.0, 'dist_basis_pct': 2.55,
        'adx': 25.0, 'plus_di': 30.0, 'minus_di': 20.0, 'adx_velocity': 'moderado',
        'ema20_phase': 'nivel_2_long', 'ema20_angle': 0.5, 'ema9_angle': 0.3,
        'mtf_score': 0.70, 'sar_trend_4h': 1, 'sar_trend_15m': 1,
        'pinescript_signal': 'Buy', 'allow_long_4h': True, 'fibonacci_zone': 2,
        'upper_5': 2250.0, 'lower_5': 2050.0
    }

    print('Logging some test evaluations...')
    results = engine.evaluate_all(context, 'long', 'scalping', '15m')
    for r in results:
        if r['score'] >= 0.40:
            await engine.log_evaluation('ETHUSDT', r, context)
            print(f"Logged {r['rule_code']} (score={r['score']})")

asyncio.run(main())
