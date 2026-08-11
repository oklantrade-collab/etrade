import asyncio
from app.core.supabase_client import get_supabase
import json

async def update_bb21():
    sb = get_supabase()
    
    rule_update = {
        'min_score': 0.9,
        'condition_ids': [218, 73, 37, 12, 222],
        'condition_weights': {
            '218': 0.2,
            '73': 0.3,
            '37': 0.1,
            '12': 0.1,
            '222': 0.3
        }
    }
    
    res = sb.table('strategy_rules_v2').update(rule_update).eq('rule_code', 'Bb21').execute()
    print("Bb21 updated in DB:", res.data)

if __name__ == '__main__':
    asyncio.run(update_bb21())
