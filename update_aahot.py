import asyncio
import sys
import json
sys.path.append('.')
from app.core.supabase_client import get_supabase

async def update_rules():
    sb = get_supabase()
    
    # 1. Update AaHot
    res = sb.table('trading_rules').select('conditions').eq('rule_code', 'AaHot').execute()
    if res.data:
        conds = res.data[0]['conditions']
        new_conds = []
        for c in conds:
            if c['indicator'] == 'fib_zone' and c['operator'] == '<=':
                c['value'] = 6
            if c['indicator'] != 'not_in_ceiling':
                new_conds.append(c)
        sb.table('trading_rules').update({'conditions': new_conds}).eq('rule_code', 'AaHot').execute()
        
    # 2. Update AaHotC
    res = sb.table('trading_rules').select('conditions').eq('rule_code', 'AaHotC').execute()
    if res.data:
        conds = res.data[0]['conditions']
        new_conds = []
        for c in conds:
            if c['indicator'] == 'fib_zone' and c['operator'] == '<=':
                c['value'] = 6
            if c['indicator'] != 'not_in_ceiling':
                new_conds.append(c)
        sb.table('trading_rules').update({'conditions': new_conds}).eq('rule_code', 'AaHotC').execute()

    # 3. Update BbHot
    res = sb.table('trading_rules').select('conditions').eq('rule_code', 'BbHot').execute()
    if res.data:
        conds = res.data[0]['conditions']
        new_conds = []
        for c in conds:
            if c['indicator'] == 'fib_zone' and c['operator'] == '>=':
                c['value'] = -6
            if c['indicator'] != 'not_in_floor':
                new_conds.append(c)
        sb.table('trading_rules').update({'conditions': new_conds}).eq('rule_code', 'BbHot').execute()

    # 4. Update BbHotC
    res = sb.table('trading_rules').select('conditions').eq('rule_code', 'BbHotC').execute()
    if res.data:
        conds = res.data[0]['conditions']
        new_conds = []
        for c in conds:
            if c['indicator'] == 'fib_zone' and c['operator'] == '>=':
                c['value'] = -6
            if c['indicator'] != 'not_in_floor':
                new_conds.append(c)
        sb.table('trading_rules').update({'conditions': new_conds}).eq('rule_code', 'BbHotC').execute()

    print("Supabase rules updated successfully.")

asyncio.run(update_rules())
