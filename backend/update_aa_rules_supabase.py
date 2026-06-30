import asyncio
import os
import sys

# Agregar la ruta raíz para importar los módulos correctamente
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from app.strategy.rule_engine import DEFAULT_RULES

async def update_rules():
    sb = get_supabase()
    
    rules_to_update = ['Aa21', 'Aa30', 'Bb30', 'Aa30C', 'Bb30C']
    for rule_code in rules_to_update:
        rule = next((r for r in DEFAULT_RULES if r['rule_code'] == rule_code), None)
        if rule:
            print(f"Updating rule {rule['rule_code']} in Supabase...")
            res = sb.table('trading_rules').update({
                'name': rule['name'],
                'description': rule['description'],
                'conditions': rule['conditions'],
                'notes': rule['notes']
            }).eq('rule_code', rule_code).execute()
            print(res)
        else:
            print(f"Rule {rule_code} not found in DEFAULT_RULES")

if __name__ == '__main__':
    asyncio.run(update_rules())
