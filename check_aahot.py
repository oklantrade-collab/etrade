import asyncio
import sys
import json
sys.path.append('.')
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    res = sb.table('strategy_evaluations').select('*').eq('symbol', 'USDJPY').eq('rule_code', 'AaHot').gte('created_at', '2026-06-29T12:00:00Z').order('created_at', desc=True).limit(5).execute()
    with open('aahot_eval.json', 'w', encoding='utf-8') as f:
        json.dump(res.data, f, indent=2)

asyncio.run(check())
