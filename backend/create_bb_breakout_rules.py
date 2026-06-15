"""
Crea nuevas condiciones y reglas para Bollinger Breakout + EMA Stack.
- Aa30: LONG Breakout (EMA3 > EMA9 > EMA20, angulos positivos, SAR 15m alcista)
- Bb30: SHORT Breakout (EMA3 < EMA9 < EMA20, angulos negativos, SAR 15m bajista)
Sin filtro macro de 4H para capturar movimientos explosivos tempranos.
"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

# 1. Obtener max IDs actuales
r1 = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
r2 = sb.table('strategy_rules_v2').select('id').order('id', desc=True).limit(1).execute()
max_cond_id = r1.data[0]['id']
max_rule_id = r2.data[0]['id']
print(f"Max condition ID actual: {max_cond_id}")
print(f"Max rule ID actual: {max_rule_id}")

# 2. Crear nuevas condiciones para EMA Stack
# Necesitamos: EMA3 > EMA9, EMA9 > EMA20 (LONG) y sus inversos (SHORT)
new_conditions = [
    {
        'id': max_cond_id + 1,
        'name': 'EMA3 > EMA9 (stack alcista)',
        'variable_id': 7,   # ema3
        'operator': '>',
        'value_type': 'variable',
        'value_literal': None,
        'value_variable': 'ema9',
        'value_list': None,
        'value_min': None,
        'value_max': None,
        'timeframe': '15m',
        'description': 'EMA3 por encima de EMA9 (alineacion alcista)'
    },
    {
        'id': max_cond_id + 2,
        'name': 'EMA9 > EMA20 (stack alcista)',
        'variable_id': 8,   # ema9
        'operator': '>',
        'value_type': 'variable',
        'value_literal': None,
        'value_variable': 'ema20',
        'value_list': None,
        'value_min': None,
        'value_max': None,
        'timeframe': '15m',
        'description': 'EMA9 por encima de EMA20 (alineacion alcista)'
    },
    {
        'id': max_cond_id + 3,
        'name': 'EMA3 < EMA9 (stack bajista)',
        'variable_id': 7,   # ema3
        'operator': '<',
        'value_type': 'variable',
        'value_literal': None,
        'value_variable': 'ema9',
        'value_list': None,
        'value_min': None,
        'value_max': None,
        'timeframe': '15m',
        'description': 'EMA3 por debajo de EMA9 (alineacion bajista)'
    },
    {
        'id': max_cond_id + 4,
        'name': 'EMA9 < EMA20 (stack bajista)',
        'variable_id': 8,   # ema9
        'operator': '<',
        'value_type': 'variable',
        'value_literal': None,
        'value_variable': 'ema20',
        'value_list': None,
        'value_min': None,
        'value_max': None,
        'timeframe': '15m',
        'description': 'EMA9 por debajo de EMA20 (alineacion bajista)'
    },
]

for c in new_conditions:
    res = sb.table('strategy_conditions').upsert(c).execute()
    print(f"  Condicion {c['id']} ({c['name']}): OK")

# 3. IDs de las nuevas condiciones
ema3_gt_ema9 = max_cond_id + 1
ema9_gt_ema20 = max_cond_id + 2
ema3_lt_ema9 = max_cond_id + 3
ema9_lt_ema20 = max_cond_id + 4

# 4. Crear las nuevas reglas
# Aa30: LONG Bollinger Breakout + EMA Stack
# Condiciones: EMA3>EMA9, EMA9>EMA20, EMA20 angulo+, EMA9 angulo+, SAR 15m alcista
# SIN filtro de SAR 4h ni Structure 4h (para capturar breakouts tempranos)
aa30_cond_ids = [ema3_gt_ema9, ema9_gt_ema20, 11, 13, 24]
aa30_weights = {
    str(ema3_gt_ema9): 0.25,
    str(ema9_gt_ema20): 0.25,
    '11': 0.20,   # EMA20 angulo positivo
    '13': 0.15,   # EMA9 angulo positivo
    '24': 0.15,   # SAR 15m alcista
}

aa30 = {
    'id': max_rule_id + 1,
    'rule_code': 'Aa30',
    'name': 'LONG Breakout: EMA Stack alcista + SAR 15m',
    'strategy_type': 'scalping',
    'direction': 'long',
    'cycle': '15m',
    'condition_ids': aa30_cond_ids,
    'condition_logic': 'AND',
    'min_score': 0.65,
    'condition_weights': aa30_weights,
    'market_types': ['crypto_futures', 'forex_futures'],
    'enabled': True,
    'priority': 1,
    'confidence': 0.75,
    'version': 1,
    'notes': 'Bollinger Breakout + EMA Stack alcista. Sin filtro macro 4H para capturar movimientos explosivos tempranos.'
}

res = sb.table('strategy_rules_v2').upsert(aa30).execute()
print(f"\nRegla Aa30 (LONG Breakout): OK - ID {aa30['id']}")

# Bb30: SHORT Bollinger Breakout + EMA Stack
# Condiciones: EMA3<EMA9, EMA9<EMA20, EMA20 angulo-, EMA9 angulo-, SAR 15m bajista
bb30_cond_ids = [ema3_lt_ema9, ema9_lt_ema20, 12, 14, 25]
bb30_weights = {
    str(ema3_lt_ema9): 0.25,
    str(ema9_lt_ema20): 0.25,
    '12': 0.20,   # EMA20 angulo negativo
    '14': 0.15,   # EMA9 angulo negativo
    '25': 0.15,   # SAR 15m bajista
}

bb30 = {
    'id': max_rule_id + 2,
    'rule_code': 'Bb30',
    'name': 'SHORT Breakout: EMA Stack bajista + SAR 15m',
    'strategy_type': 'scalping',
    'direction': 'short',
    'cycle': '15m',
    'condition_ids': bb30_cond_ids,
    'condition_logic': 'AND',
    'min_score': 0.65,
    'condition_weights': bb30_weights,
    'market_types': ['crypto_futures', 'forex_futures'],
    'enabled': True,
    'priority': 1,
    'confidence': 0.75,
    'version': 1,
    'notes': 'Bollinger Breakout + EMA Stack bajista. Sin filtro macro 4H para capturar movimientos explosivos tempranos.'
}

res = sb.table('strategy_rules_v2').upsert(bb30).execute()
print(f"Regla Bb30 (SHORT Breakout): OK - ID {bb30['id']}")

print("\n" + "=" * 60)
print("RESUMEN DE CAMBIOS")
print("=" * 60)
print(f"Nuevas condiciones creadas: {max_cond_id+1} a {max_cond_id+4}")
print(f"  {ema3_gt_ema9}: EMA3 > EMA9 (stack alcista)")
print(f"  {ema9_gt_ema20}: EMA9 > EMA20 (stack alcista)")
print(f"  {ema3_lt_ema9}: EMA3 < EMA9 (stack bajista)")
print(f"  {ema9_lt_ema20}: EMA9 < EMA20 (stack bajista)")
print(f"\nNuevas reglas creadas:")
print(f"  Aa30: LONG Breakout  -> Condiciones: {aa30_cond_ids}")
print(f"  Bb30: SHORT Breakout -> Condiciones: {bb30_cond_ids}")
print(f"\nMercados: crypto_futures, forex_futures")
print(f"Sin filtro macro 4H (SAR 4h / Structure 4h)")
print("=" * 60)
