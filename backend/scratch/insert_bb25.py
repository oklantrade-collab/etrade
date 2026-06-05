import os
import sys
from dotenv import load_dotenv
from supabase import create_client

sys.path.append('c:/Fuentes/eTrade/backend')
load_dotenv('c:/Fuentes/eTrade/backend/.env')
sb = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_KEY'))

async def main():
    print("=== REGISTERING Bb25 RULE IN SUPABASE ===")
    
    # 1. Define rule data matching exactly strategy_rules_v2 schema
    bb25_rule = {
        'id': 21,
        'rule_code': 'Bb25',
        'name': 'SHORT Cruce EMA3 < EMA9 en Tendencia',
        'strategy_type': 'scalping',
        'direction': 'short',
        'cycle': '5m',
        'condition_ids': [229, 214, 215, 226, 75],
        'condition_logic': 'AND',
        'min_score': 0.7,
        'condition_weights': {
            '229': 0.25,
            '214': 0.25,
            '215': 0.25,
            '226': 0.15,
            '75': 0.1
        },
        'market_types': ['crypto_futures', 'forex_futures'],
        'applicable_cycles': ['5m'],
        'enabled': True,
        'priority': 1,
        'confidence': 0.8,
        'version': 1,
        'notes': 'Regla espejo simétrica de Aa25 para continuación bajista en 5m.'
    }
    
    # Check if Bb25 already exists
    existing = sb.table('strategy_rules_v2').select('id').eq('rule_code', 'Bb25').execute()
    if not existing.data:
        print("Inserting new rule Bb25...")
        sb.table('strategy_rules_v2').insert(bb25_rule).execute()
    else:
        print("Rule Bb25 already exists, updating...")
        sb.table('strategy_rules_v2').update(bb25_rule).eq('rule_code', 'Bb25').execute()
        
    print("=== Bb25 RULE REGISTRATION COMPLETED ===")

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
