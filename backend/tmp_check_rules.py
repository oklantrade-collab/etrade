from app.core.supabase_client import get_supabase
import asyncio

async def check_rules():
    sb = get_supabase()
    res = sb.table('strategy_rules_v2').select('*').in_('rule_code', ['Dd21_15m', 'Dd21_4h']).execute()
    for rule in res.data:
        print(f"Code: {rule['rule_code']}, Conditions: {rule['condition_ids']}")

if __name__ == "__main__":
    asyncio.run(check_rules())
