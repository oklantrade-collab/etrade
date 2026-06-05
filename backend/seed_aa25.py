import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.strategy.rule_engine import DEFAULT_RULES
from app.core.supabase_client import get_supabase

async def seed_new_rule():
    sb = get_supabase()
    
    # Extract Aa25
    rule = next((r for r in DEFAULT_RULES if r['rule_code'] == 'Aa25'), None)
    if not rule:
        print("Rule Aa25 not found in DEFAULT_RULES")
        return
        
    print(f"Upserting rule: {rule['rule_code']}")
    
    # Upsert the rule into strategy_rules_v2
    # Ensure id is 1011
    res = sb.table('strategy_rules_v2').upsert({
        'id': rule['id'],
        'rule_code': rule['rule_code'],
        'name': rule['name'],
        'description': rule['description'],
        'direction': rule['direction'],
        'market_type': rule['market_type'],
        'ema50_vs_ema200': rule['ema50_vs_ema200'],
        'enabled': rule['enabled'],
        'regime_allowed': rule['regime_allowed'],
        'priority': rule['priority'],
        'confidence': rule['confidence'],
        'entry_trades': rule['entry_trades'],
        'conditions': rule['conditions'],
        'logic_operator': rule['logic'],
        'notes': rule['notes']
    }).execute()
    
    print("Rule Aa25 seeded successfully.")

if __name__ == "__main__":
    asyncio.run(seed_new_rule())
