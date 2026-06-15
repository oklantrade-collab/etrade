"""
Actualiza las reglas Aa30 y Bb30 para operar en 5m, y crea/actualiza las condiciones necesarias.
"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

# 1. Obtener max IDs
r1 = sb.table('strategy_conditions').select('id').order('id', desc=True).limit(1).execute()
max_cond_id = r1.data[0]['id']

# 2. Actualizar las 4 condiciones que creamos antes a 5m (ema3_5m > ema9_5m, etc)
# Los IDs de las 4 condiciones anteriores eran 9904, 9905, 9906, 9907
sb.table('strategy_conditions').update({'timeframe': '5m', 'variable_id': None, 'value_variable': 'ema9_5m', 'name': 'EMA3 > EMA9 5m'}).eq('id', 9904).execute()
sb.table('strategy_conditions').update({'timeframe': '5m', 'variable_id': None, 'value_variable': 'ema20_5m', 'name': 'EMA9 > EMA20 5m'}).eq('id', 9905).execute()
sb.table('strategy_conditions').update({'timeframe': '5m', 'variable_id': None, 'value_variable': 'ema9_5m', 'name': 'EMA3 < EMA9 5m'}).eq('id', 9906).execute()
sb.table('strategy_conditions').update({'timeframe': '5m', 'variable_id': None, 'value_variable': 'ema20_5m', 'name': 'EMA9 < EMA20 5m'}).eq('id', 9907).execute()

# También necesitamos actualizar el 'source_field' en strategy_variables o decirle a strategy_engine que use una variable virtual.
# En el engine v2, si `variable_id` es nulo, usará el context usando `cond.get('variable')`. 
# Espera, si `variable_id` es None, `variable.get('source_field')` fallará si no está mappeado.
# Mejor creamos variables virtuales si no existen.
r_vars = sb.table('strategy_variables').select('id').order('id', desc=True).limit(1).execute()
max_var_id = r_vars.data[0]['id']

new_vars = [
    {'id': max_var_id+1, 'name': 'ema3_5m', 'source_field': 'ema3_5m', 'category': 'ema', 'timeframes': ['5m'], 'data_type': 'float'},
    {'id': max_var_id+2, 'name': 'ema9_5m', 'source_field': 'ema9_5m', 'category': 'ema', 'timeframes': ['5m'], 'data_type': 'float'},
    {'id': max_var_id+3, 'name': 'ema20_5m', 'source_field': 'ema20_5m', 'category': 'ema', 'timeframes': ['5m'], 'data_type': 'float'},
    {'id': max_var_id+4, 'name': 'ema9_angle_5m', 'source_field': 'ema9_angle_5m', 'category': 'ema', 'timeframes': ['5m'], 'data_type': 'float'},
    {'id': max_var_id+5, 'name': 'ema20_angle_5m', 'source_field': 'ema20_angle_5m', 'category': 'ema', 'timeframes': ['5m'], 'data_type': 'float'},
    {'id': max_var_id+6, 'name': 'sar_trend_5m', 'source_field': 'sar_trend_5m', 'category': 'sar', 'timeframes': ['5m'], 'data_type': 'integer'}
]
for v in new_vars:
    sb.table('strategy_variables').upsert(v).execute()

# Ahora actualizamos las condiciones 9904-9907 con los nuevos variable_id
sb.table('strategy_conditions').update({'variable_id': max_var_id+1}).eq('id', 9904).execute() # ema3_5m
sb.table('strategy_conditions').update({'variable_id': max_var_id+2}).eq('id', 9905).execute() # ema9_5m
sb.table('strategy_conditions').update({'variable_id': max_var_id+1}).eq('id', 9906).execute() # ema3_5m
sb.table('strategy_conditions').update({'variable_id': max_var_id+2}).eq('id', 9907).execute() # ema9_5m

# Y creamos 3 nuevas condiciones para 5m: EMA20 angulo+, EMA9 angulo+, SAR 5m alcista, y sus opuestos
new_conds_5m = [
    {'id': max_cond_id+1, 'name': 'EMA20 ángulo positivo 5m', 'variable_id': max_var_id+5, 'operator': '>=', 'value_type': 'literal', 'value_literal': '0', 'timeframe': '5m'},
    {'id': max_cond_id+2, 'name': 'EMA9 ángulo positivo 5m', 'variable_id': max_var_id+4, 'operator': '>=', 'value_type': 'literal', 'value_literal': '0', 'timeframe': '5m'},
    {'id': max_cond_id+3, 'name': 'SAR 5m alcista', 'variable_id': max_var_id+6, 'operator': '==', 'value_type': 'literal', 'value_literal': '1', 'timeframe': '5m'},
    {'id': max_cond_id+4, 'name': 'EMA20 ángulo negativo 5m', 'variable_id': max_var_id+5, 'operator': '<', 'value_type': 'literal', 'value_literal': '0', 'timeframe': '5m'},
    {'id': max_cond_id+5, 'name': 'EMA9 ángulo negativo 5m', 'variable_id': max_var_id+4, 'operator': '<', 'value_type': 'literal', 'value_literal': '0', 'timeframe': '5m'},
    {'id': max_cond_id+6, 'name': 'SAR 5m bajista', 'variable_id': max_var_id+6, 'operator': '==', 'value_type': 'literal', 'value_literal': '-1', 'timeframe': '5m'},
]
for c in new_conds_5m:
    sb.table('strategy_conditions').upsert(c).execute()

c_ema20_pos_5m = max_cond_id+1
c_ema9_pos_5m  = max_cond_id+2
c_sar_pos_5m   = max_cond_id+3
c_ema20_neg_5m = max_cond_id+4
c_ema9_neg_5m  = max_cond_id+5
c_sar_neg_5m   = max_cond_id+6

# Actualizar Aa30 y Bb30
aa30_conds = [9904, 9905, c_ema20_pos_5m, c_ema9_pos_5m, c_sar_pos_5m]
aa30_weights = {str(c): 0.20 for c in aa30_conds}

sb.table('strategy_rules_v2').update({
    'cycle': '5m',
    'condition_ids': aa30_conds,
    'condition_weights': aa30_weights,
    'name': 'LONG Breakout 5m: EMA Stack + SAR 5m'
}).eq('rule_code', 'Aa30').execute()

bb30_conds = [9906, 9907, c_ema20_neg_5m, c_ema9_neg_5m, c_sar_neg_5m]
bb30_weights = {str(c): 0.20 for c in bb30_conds}

sb.table('strategy_rules_v2').update({
    'cycle': '5m',
    'condition_ids': bb30_conds,
    'condition_weights': bb30_weights,
    'name': 'SHORT Breakout 5m: EMA Stack + SAR 5m'
}).eq('rule_code', 'Bb30').execute()

print("¡Reglas Aa30 y Bb30 actualizadas exitosamente a 5 minutos!")
print(f"Condiciones Aa30: {aa30_conds}")
print(f"Condiciones Bb30: {bb30_conds}")
