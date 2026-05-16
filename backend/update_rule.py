import asyncio
import os
import sys

# Agregar la ruta raíz para importar los módulos correctamente
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase
from app.strategy.rule_engine import DEFAULT_RULES

async def update_rule():
    sb = get_supabase()
    
    rule = next((r for r in DEFAULT_RULES if r['rule_code'] == 'Aa12'), None)
    if rule:
        print(f"Updating rule {rule['rule_code']} in Supabase...")
        res = sb.table('trading_rules').update({
            'conditions': rule['conditions'],
            'notes': rule['notes']
        }).eq('rule_code', 'Aa12').execute()
        print(res)

if __name__ == '__main__':
    asyncio.run(update_rule())
