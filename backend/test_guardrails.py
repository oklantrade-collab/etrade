import asyncio
import os
from dotenv import load_dotenv
from supabase import create_client
from app.core.parameter_guard import validate_parameter_change

load_dotenv()
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

async def run_tests():
    print("=== TEST 1: CAMBIO ACEPTADO (DENTRO DE RANGO, EV > 0) ===")
    # rr_min_riesgo_medio: 2.5 -> 2.3 | win_rate=0.50, avg_rr=2.3
    res1 = await validate_parameter_change(
        'rr_min_riesgo_medio', 2.3, 'antigravity_test', 'Optimización riesgo medio',
        backtest_result={'win_rate': 0.50, 'avg_rr': 2.3, 'total_trades': 20},
        supabase_client=sb
    )
    print(f"Resultado: {'ACCEPTED' if res1.accepted else 'REJECTED'}")
    print(f"Razon: {res1.reason}")
    print(f"EV: {res1.expected_value}")

    print("\n=== TEST 2: CAMBIO RECHAZADO (FUERA DE RANGO / OOB) ===")
    # rr_min_riesgo_medio: 2.5 -> 1.2 (Min es 1.5)
    res2 = await validate_parameter_change(
        'rr_min_riesgo_medio', 1.2, 'antigravity_test', 'Prueba OOB',
        backtest_result={'win_rate': 0.50, 'avg_rr': 1.2, 'total_trades': 20},
        supabase_client=sb
    )
    print(f"Resultado: {'ACCEPTED' if res2.accepted else 'REJECTED'}")
    print(f"Razon: {res2.reason}")

    print("\n=== TEST 3: CAMBIO RECHAZADO (EV NEGATIVO) ===")
    # rr_min_bajo_riesgo: 2.0 -> 1.6 | win_rate=0.35, avg_rr=1.6
    # EV = (0.35*1.6) - 0.65 = 0.56 - 0.65 = -0.09
    res3 = await validate_parameter_change(
        'rr_min_bajo_riesgo', 1.6, 'antigravity_test', 'Prueba EV Negativo',
        backtest_result={'win_rate': 0.35, 'avg_rr': 1.6, 'total_trades': 20},
        supabase_client=sb
    )
    print(f"Resultado: {'ACCEPTED' if res3.accepted else 'REJECTED'}")
    print(f"Razon: {res3.reason}")
    print(f"EV: {res3.expected_value}")

if __name__ == "__main__":
    asyncio.run(run_tests())
