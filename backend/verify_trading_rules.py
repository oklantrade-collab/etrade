import os
import sys
from dotenv import load_dotenv
from supabase import create_client

# Ensure backend root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'),
                   os.getenv('SUPABASE_SERVICE_KEY'))

async def verify():
    # Verificacion 1 - Conteo total
    res = sb.table('trading_rules')\
        .select('id, rule_code, direction, enabled, version')\
        .gte('id', 1001)\
        .lte('id', 1013)\
        .order('id')\
        .execute()

    rules = res.data
    print(f"Total reglas encontradas: {len(rules)} (esperado: 13)")
    assert len(rules) == 13, \
        f"ERROR: Se esperaban 13 reglas, hay {len(rules)}"

    # Verificacion 2 - Rule codes correctos
    expected = {
        1001: 'Aa13', 1002: 'Aa12', 1003: 'Aa11',
        1004: 'Aa24', 1005: 'Aa22', 1006: 'Aa23',
        1007: 'Aa21', 1008: 'Bb12', 1009: 'Bb13',
        1010: 'Bb11', 1011: 'Bb22', 1012: 'Bb23',
        1013: 'Bb21'
    }

    print("\nVerificacion de rule_codes:")
    all_ok = True
    for rule in rules:
        expected_code = expected.get(rule['id'])
        status = 'OK' if rule['rule_code'] == expected_code else 'ERROR'
        if status == 'ERROR':
            all_ok = False
        print(f"  [{status}] id={rule['id']} "
              f"rule_code={rule['rule_code']} "
              f"(esperado: {expected_code}) "
              f"v{rule['version']}")

    # Verificacion 3 - Distribución long/short
    long_rules  = [r for r in rules if r['rule_code'].startswith('Aa')]
    short_rules = [r for r in rules if r['rule_code'].startswith('Bb')]
    active      = [r for r in rules if r['enabled']]

    print(f"\nReglas LONG (Aa):  {len(long_rules)} (esperado: 7)")
    print(f"Reglas SHORT (Bb): {len(short_rules)} (esperado: 6)")
    print(f"Reglas activas:    {len(active)} (esperado: 13)")

    assert len(long_rules)  == 7,  "ERROR: se esperaban 7 reglas LONG"
    assert len(short_rules) == 6,  "ERROR: se esperaban 6 reglas SHORT"
    assert len(active)      == 13, "ERROR: todas deben estar activas"

    if all_ok:
        print("\nTODAS LAS VERIFICACIONES PASARON")
    else:
        print("\nERROR: Hay reglas con rule_code incorrecto")
        print("Ejecutar el seed nuevamente con UPSERT")

if __name__ == "__main__":
    import asyncio
    asyncio.run(verify())
