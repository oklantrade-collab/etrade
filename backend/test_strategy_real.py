
import asyncio, os
from dotenv import load_dotenv
from supabase import create_client
from app.strategy.strategy_engine import StrategyEngine

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

async def main():
    print("=== TEST STRATEGY ENGINE (REAL DB) ===")
    engine = StrategyEngine(sb)
    await engine.load()

    print(f"Reglas cargadas: {len(engine.rules)}")
    print(f"Condiciones:     {len(engine.conditions)}")
    print(f"Variables:       {len(engine.variables)}")

    if not engine.rules:
        print("ERROR: No se cargaron reglas. Verifica la tabla strategy_rules_v2.")
        return

    # Simular contexto ETH favorable para Aa22 (Regla principal LONG)
    # Aa22 conditions: {8,2,26,32,36,40}
    # 8: EMA20 fase long (1-3)
    # 2: ADX fuerte (>35? No, variable 2 is dist_basis_pct. Wait, let's check variable ids)
    # Checking variables: 1=price, 2=dist_basis_pct, 3=adx, ...
    # Checking conditions: 2=ADX moderado (20-35)
    
    context = {
        'price': 2161.0,
        'dist_basis_pct': 2.55,
        'adx': 25.0, # Moderado
        'plus_di': 30.0,
        'minus_di': 20.0,
        'adx_velocity': 'moderado',
        'ema20_phase': 'nivel_2_long',
        'ema20_angle': 0.5,
        'mtf_score': 0.70,
        'sar_trend_4h': 1,
        'sar_trend_15m': 1,
        'pinescript_signal': 'Buy',
        'allow_long_4h': True,
        'fibonacci_zone': 2,
        'upper_5': 2250.0,
        'lower_5': 2050.0
    }

    print('\nEvaluating SCALPING LONG 15m...')
    results = engine.evaluate_all(context, 'long', 'scalping', '15m')
    for r in results:
        status = '✅ TRIGGERED' if r['triggered'] else '❌'
        print(f"{status} {r['rule_code']}: score={r['score']:.2f} (min={r['min_score']})")
        if not r['triggered'] and r['score'] > 0:
            # Mostrar qué condiciones fallaron
            for cid, detail in r['conditions'].items():
                if not detail['passed']:
                    print(f"   - Falla: {detail['name']} (Valor actual: {detail['value']})")

asyncio.run(main())
