import asyncio
import os
import sys
sys.path.append('c:/Fuentes/eTrade/backend')
from app.core.supabase_client import get_supabase

def update_aa13_market_types():
    sb = get_supabase()
    print("Fetching Aa13...")
    res = sb.table('strategy_rules_v2').select('*').eq('rule_code', 'Aa13').execute()
    if not res.data:
        print("Rule Aa13 not found in DB.")
        return
    rule = res.data[0]
    market_types = rule.get('market_types', [])
    if isinstance(market_types, str):
        import json
        market_types = json.loads(market_types)
    
    if 'forex_futures' not in market_types:
        market_types.append('forex_futures')
        print(f"Updating market_types to: {market_types}")
        update_res = sb.table('strategy_rules_v2').update({'market_types': market_types}).eq('rule_code', 'Aa13').execute()
        print("Update response:", update_res)
    else:
        print("forex_futures is already in market_types:", market_types)

if __name__ == "__main__":
    update_aa13_market_types()
