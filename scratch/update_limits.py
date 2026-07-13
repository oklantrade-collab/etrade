import asyncio
import sys
import os
import json
sys.path.append('.')
from app.core.supabase_client import get_supabase

async def update_limit_rules():
    sb = get_supabase()
    
    rules = [
        {
            'rule_code': 'Dd11',
            'name': 'Swing LONG Extremo Banda',
            'description': 'LIMIT en extremo inferior (lower_5/lower_6) con RSI o Bollinger',
            'direction': 'long',
            'confidence': 0.95,
            'enabled': True,
            'priority': 20,
            'market_type': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'conditions': [
                {"indicator": "dd11_limit_ok", "operator": "==", "value": True}
            ]
        },
        {
            'rule_code': 'Dd12',
            'name': 'Swing SHORT Extremo Banda',
            'description': 'LIMIT en extremo superior (upper_5/upper_6) con RSI o Bollinger',
            'direction': 'short',
            'confidence': 0.95,
            'enabled': True,
            'priority': 20,
            'market_type': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'conditions': [
                {"indicator": "dd12_limit_ok", "operator": "==", "value": True}
            ]
        },
        {
            'rule_code': 'Aa21',
            'name': 'Trend Pullback LONG (EMA20)',
            'description': 'LIMIT en EMA20 durante tendencia alcista fuerte',
            'direction': 'long',
            'confidence': 0.85,
            'enabled': True,
            'priority': 25,
            'market_type': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'conditions': [
                {"indicator": "aa21_limit_ok", "operator": "==", "value": True}
            ]
        },
        {
            'rule_code': 'Bb21',
            'name': 'Trend Pullback SHORT (EMA20)',
            'description': 'LIMIT en EMA20 durante tendencia bajista extrema',
            'direction': 'short',
            'confidence': 0.85,
            'enabled': True,
            'priority': 25,
            'market_type': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'conditions': [
                {"indicator": "bb21_limit_ok", "operator": "==", "value": True}
            ]
        },
        {
            'rule_code': 'Aa40',
            'name': 'Capitulation Flash Crash LONG',
            'description': 'LIMIT pasivo profundo atrapa-wicks en pánico extremo',
            'direction': 'long',
            'confidence': 0.99,
            'enabled': True,
            'priority': 10,
            'market_type': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'conditions': [
                {"indicator": "aa40_limit_ok", "operator": "==", "value": True}
            ]
        },
        {
            'rule_code': 'Bb40',
            'name': 'Euphoria Flash Crash SHORT',
            'description': 'LIMIT pasivo alto atrapa-wicks en euforia extrema',
            'direction': 'short',
            'confidence': 0.99,
            'enabled': True,
            'priority': 10,
            'market_type': ['crypto_futures', 'forex_futures', 'crypto_spot'],
            'conditions': [
                {"indicator": "bb40_limit_ok", "operator": "==", "value": True}
            ]
        }
    ]

    for table in ['trading_rules']:
        # get max id
        res = sb.table(table).select('id').order('id', desc=True).limit(1).execute()
        max_id = int(res.data[0]['id']) if res.data else 0
        
        for rule in rules:
            try:
                # Check if exists
                res = sb.table(table).select('rule_code').eq('rule_code', rule['rule_code']).execute()
                if res.data:
                    # Update
                    sb.table(table).update(rule).eq('rule_code', rule['rule_code']).execute()
                    print(f"Updated {rule['rule_code']} in {table}")
                else:
                    max_id += 1
                    rule['id'] = max_id
                    sb.table(table).insert(rule).execute()
                    print(f"Inserted {rule['rule_code']} in {table}")
            except Exception as e:
                print(f"Error {table} {rule['rule_code']}: {e}")

if __name__ == "__main__":
    asyncio.run(update_limit_rules())
