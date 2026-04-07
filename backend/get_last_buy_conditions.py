import asyncio
import os
import sys
import json
from datetime import datetime

# Añadir el path base para importar app
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.core.supabase_client import get_supabase

async def get_last_buy_info():
    sb = get_supabase()
    
    print("--- Buscando las últimas 5 compras (paper_trades) ---")
    # Buscar en paper_trades las compras más recientes que tengan un rule_code
    res = sb.table('paper_trades').select('*').not_.is_('rule_code', 'null').order('created_at', desc=True).limit(5).execute()
    
    if not res.data:
        print("No se encontraron trades con regla en paper_trades.")
        return

    print("Trades recientes encontrados:")
    for t in res.data:
        print(f" - {t['created_at']} | {t['symbol']} | Rule: {t['rule_code']}")

    # Tomar la primera que no sea 'TEST'
    last_trade = next((t for t in res.data if t['rule_code'] != 'TEST'), res.data[0])
    
    rule_code = last_trade.get('rule_code')
    symbol = last_trade.get('symbol')
    created_at = last_trade.get('created_at')
    
    # Intentar buscar la evaluación correspondiente
    eval_res = sb.table('strategy_evaluations').select('*').eq('rule_code', rule_code).eq('symbol', symbol).order('created_at', desc=True).limit(1).execute()
    last_eval = eval_res.data[0] if eval_res.data else {}
    score = last_eval.get('score')
    
    print(f"Última compra detectada:")
    print(f"  Símbolo: {symbol}")
    print(f"  Regla (Rule Code): {rule_code}")
    print(f"  Fecha: {created_at}")
    print(f"  Score: {score}")
    
    if not rule_code:
        print("No se encontró rule_code.")
        return

    print(f"\n--- Buscando detalles de la regla {rule_code} ---")
    
    # Obtener la regla de strategy_rules_v2
    # Nota: Usamos strategy_rules_v2 segun la migracion 023
    rule_res = sb.table('strategy_rules_v2').select('*').eq('rule_code', rule_code).execute()
    if not rule_res.data:
        print(f"No se encontró la regla con código {rule_code} en strategy_rules_v2")
        return
        
    rule = rule_res.data[0]
    rule_id = rule['id']
    condition_ids = rule.get('condition_ids', [])
    weights = rule.get('condition_weights', {})
    
    print(f"Regla: {rule['name']}")
    print(f"Descripción: {rule.get('notes')}")
    print(f"Dirección: {rule.get('direction')}")
    print(f"Ciclo: {rule.get('cycle')}")
    print(f"Score mínimo requerido: {rule.get('min_score')}")

    # Obtener las condiciones específicas que componen esta regla
    if not condition_ids:
        print("La regla no tiene condition_ids.")
        return

    cond_res = sb.table('strategy_conditions').select('*, strategy_variables(*)').in_('id', condition_ids).execute()
    
    if not cond_res.data:
        print(f"No se encontraron condiciones en strategy_conditions para los IDs: {condition_ids}")
        return

    print("\nCondiciones de la regla:")
    # Mapear condiciones para mostrar el peso
    for c in cond_res.data:
        cid = str(c['id'])
        weight = weights.get(cid, 0)
        var = c.get('strategy_variables', {})
        print(f"- [Cond ID: {cid}] {c['name']}")
        print(f"  Variable: {var.get('name')} ({var.get('description', '')})")
        val_info = c.get('value_literal') or c.get('value_variable') or c.get('value_list') or f"{c.get('value_min')} a {c.get('value_max')}"
        print(f"  Operador: {c['operator']} | Valor: {val_info}")
        print(f"  Timeframe: {c.get('timeframe')}")
        print(f"  Peso (Weight): {weight}")

    # Si tenemos contexto de la evaluación, mostrar los valores que se usaron
    context = last_eval.get('context', {})
    if context:
        print("\nValores de indicadores en el momento de la entrada:")
        for k, v in context.items():
            print(f"  {k}: {v}")

if __name__ == "__main__":
    asyncio.run(get_last_buy_info())
