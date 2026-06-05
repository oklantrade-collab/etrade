import asyncio, json
from app.core.supabase_client import get_supabase

async def run():
    sb = get_supabase()
    res2 = sb.table('strategy_evaluations').select('rule_code, score, reason, created_at').eq('symbol', 'ADAUSDT').gte('created_at', '2026-05-28T12:25:00Z').lte('created_at', '2026-05-28T12:50:00Z').execute()
    for row in res2.data:
        if 'AaHot' in row['rule_code'] or 'Aa21' in row['rule_code']:
            print(f"{row['created_at']} | {row['rule_code']} | Score: {row['score']} | Reason: {row['reason']}")

asyncio.run(run())
