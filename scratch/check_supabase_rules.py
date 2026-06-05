import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv('c:/Fuentes/eTrade/backend/.env')
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_SERVICE_KEY')
sb = create_client(url, key)

async def check():
    # Check trading_rules
    print("=== TRADING RULES in Supabase ===")
    res1 = sb.table('trading_rules').select('id, rule_code, name, conditions, market_type').in_('rule_code', ['Aa21', 'Bb21', 'Aa_HOT', 'Bb_HOT', 'AaHot', 'BbHot']).execute()
    for row in res1.data:
        print(f"ID: {row['id']} | Code: {row['rule_code']} | Name: {row['name']} | Markets: {row['market_type']}")
        print(f"  Conditions: {row['conditions']}")
        print("-" * 50)
        
    # Check strategy_rules_v2
    print("\n=== STRATEGY RULES V2 in Supabase ===")
    res2 = sb.table('strategy_rules_v2').select('id, rule_code, name, condition_ids, market_types').in_('rule_code', ['Aa21', 'Bb21', 'Aa_HOT', 'Bb_HOT', 'AaHot', 'BbHot']).execute()
    for row in res2.data:
        print(f"ID: {row['id']} | Code: {row['rule_code']} | Name: {row['name']} | Markets: {row['market_types']}")
        print(f"  Condition IDs: {row['condition_ids']}")
        print("-" * 50)

if __name__ == '__main__':
    asyncio.run(check())
