import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client
import sys

# Ensure backend root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.parameter_guard import (
    get_active_params,
    REGIME_PARAM_NAMES,
    GLOBAL_PARAM_NAMES
)

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'),
                   os.getenv('SUPABASE_SERVICE_KEY'))

async def test():
    # Obtener todos los nombres en Supabase
    res = sb.table('parameter_bounds')\
        .select('parameter_name')\
        .execute()
    db_names = {r['parameter_name'] for r in res.data}

    print("Verificando que todos los nombres del mapeo")
    print("existen en parameter_bounds de Supabase:\n")

    all_ok = True

    for regime, mapping in REGIME_PARAM_NAMES.items():
        print(f"Regimen: {regime}")
        for param_key, db_name in mapping.items():
            exists = db_name in db_names
            status = 'OK' if exists else 'ERROR - NO EXISTE EN DB'
            if not exists:
                all_ok = False
            print(f"  [{status}] {param_key} -> '{db_name}'")

    print(f"\nParametros globales:")
    for param_key, db_name in GLOBAL_PARAM_NAMES.items():
        exists = db_name in db_names
        status = 'OK' if exists else 'ERROR - NO EXISTE EN DB'
        if not exists:
            all_ok = False
        print(f"  [{status}] {param_key} -> '{db_name}'")

    print(f"\n{'TODOS LOS NOMBRES SON CORRECTOS' if all_ok else 'HAY NOMBRES INCORRECTOS - CORREGIR'}")

    if all_ok:
        # Test funcional: obtener params para los 3 regimenes
        print("\nTest funcional - obtener params para cada regimen:")
        for regime in ['bajo_riesgo', 'riesgo_medio', 'alto_riesgo']:
            params = get_active_params(regime, sb)
            mtf = params.get('mtf_threshold', 'FALTANTE')
            rr  = params.get('rr_min', 'FALTANTE')
            print(f"  {regime}: mtf_threshold={mtf} rr_min={rr}")

            assert mtf != 'FALTANTE', \
                f"mtf_threshold faltante para {regime}"
            assert rr  != 'FALTANTE', \
                f"rr_min faltante para {regime}"

        print("\nTODOS LOS TESTS DE MAPEO PASARON")

if __name__ == "__main__":
    asyncio.run(test())
