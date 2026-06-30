import asyncio
import sys
import json
sys.path.append('.')
from app.core.supabase_client import get_supabase

async def check():
    sb = get_supabase()
    res = sb.table('trading_rules').select('rule_code, name, conditions, market_type, enabled').eq('enabled', True).execute()
    with open('forex_rules_output.txt', 'w', encoding='utf-8') as f:
        for row in res.data:
            if 'forex_futures' in row.get('market_type', []) or 'forex' in row.get('market_type', []):
                f.write(f"Rule: {row['rule_code']} ({row['name']}) - {row['market_type']}\n")
                for cond in row.get('conditions', []):
                    f.write(f"  - {cond}\n")

asyncio.run(check())
