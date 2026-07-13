import asyncio
import sys
import uuid
sys.path.append('.')
from app.core.supabase_client import get_supabase

async def update_v2_rules():
    sb = get_supabase()
    
    rules = [
        {
            'rule_code': 'Dd11',
            'name': 'Swing LONG Extremo Banda',
            'strategy_type': 'swing',
            'direction': 'long',
            'enabled': True,
            'priority': 20,
            'confidence': 0.95,
            'market_types': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'applicable_cycles': ['15m', '4h'],
            'cycle': '15m',
            'condition_ids': []
        },
        {
            'rule_code': 'Dd12',
            'name': 'Swing SHORT Extremo Banda',
            'strategy_type': 'swing',
            'direction': 'short',
            'enabled': True,
            'priority': 20,
            'confidence': 0.95,
            'market_types': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'applicable_cycles': ['15m', '4h'],
            'cycle': '15m',
            'condition_ids': []
        },
        {
            'rule_code': 'Aa21',
            'name': 'Trend Pullback LONG (EMA20)',
            'strategy_type': 'trend',
            'direction': 'long',
            'enabled': True,
            'priority': 25,
            'confidence': 0.85,
            'market_types': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'applicable_cycles': ['15m', '4h'],
            'cycle': '15m',
            'condition_ids': []
        },
        {
            'rule_code': 'Bb21',
            'name': 'Trend Pullback SHORT (EMA20)',
            'strategy_type': 'trend',
            'direction': 'short',
            'enabled': True,
            'priority': 25,
            'confidence': 0.85,
            'market_types': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'applicable_cycles': ['15m', '4h'],
            'cycle': '15m',
            'condition_ids': []
        },
        {
            'rule_code': 'Aa40',
            'name': 'Capitulation Flash Crash LONG',
            'strategy_type': 'reversal',
            'direction': 'long',
            'enabled': True,
            'priority': 10,
            'confidence': 0.99,
            'market_types': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'applicable_cycles': ['15m'],
            'cycle': '15m',
            'condition_ids': []
        },
        {
            'rule_code': 'Bb40',
            'name': 'Euphoria Flash Crash SHORT',
            'strategy_type': 'reversal',
            'direction': 'short',
            'enabled': True,
            'priority': 10,
            'confidence': 0.99,
            'market_types': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'applicable_cycles': ['15m'],
            'cycle': '15m',
            'condition_ids': []
        }
    ]

    res = sb.table('strategy_rules_v2').select('id').order('id', desc=True).limit(1).execute()
    max_id = int(res.data[0]['id']) if res.data else 0

    for rule in rules:
        try:
            res = sb.table('strategy_rules_v2').select('rule_code').eq('rule_code', rule['rule_code']).execute()
            if res.data:
                sb.table('strategy_rules_v2').update(rule).eq('rule_code', rule['rule_code']).execute()
                print(f"Updated {rule['rule_code']} in strategy_rules_v2")
            else:
                max_id += 1
                rule['id'] = max_id
                sb.table('strategy_rules_v2').insert(rule).execute()
                print(f"Inserted {rule['rule_code']} in strategy_rules_v2")
        except Exception as e:
            print(f"Error {rule['rule_code']}: {e}")

if __name__ == "__main__":
    asyncio.run(update_v2_rules())
