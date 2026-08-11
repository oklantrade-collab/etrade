import asyncio
from app.core.supabase_client import get_supabase
import json

async def update_aa23():
    sb = get_supabase()
    
    rule_update = {
        'min_score': 0.8,
        'enabled': True,
        'condition_ids': [36, 11, 75, 28, 74],
        'condition_weights': {
            '36': 0.1,
            '11': 0.1,
            '75': 0.3,
            '28': 0.2,
            '74': 0.3
        }
    }
    
    res = sb.table('strategy_rules_v2').update(rule_update).eq('rule_code', 'Aa23').execute()
    print("Aa23 updated in DB:", res.data)

if __name__ == '__main__':
    asyncio.run(update_aa23())
